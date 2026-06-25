#!/usr/bin/env python
"""Read-only local inventory probe for a user-specified MiYouShe app data directory."""

from __future__ import annotations

import argparse
import json
import os
import re
import sqlite3
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[2]
OUTPUT_DIR = PROJECT_ROOT / "data" / "probes"

TEXT_EXTENSIONS = {".json", ".txt", ".html", ".htm", ".log"}
SQLITE_EXTENSIONS = {".sqlite", ".sqlite3", ".db"}
SENSITIVE_PATH_RE = re.compile(
    r"(?i)(cookie|cookies|token|stoken|ltoken|session|sessions|storage|login|auth|credential|secret)"
)

SECRET_VALUE_RE = re.compile(
    r"(?i)\b(cookie|token|stoken|ltoken|session|auth|authorization)\b"
    r"(\s*[:=]\s*)"
    r"([^,\s;\"']+)"
)
BEARER_RE = re.compile(r"(?i)\b(Bearer\s+)[A-Za-z0-9._\-+/=]+")
EMAIL_RE = re.compile(r"(?i)\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b")
PHONE_RE = re.compile(r"(?<!\d)1[3-9]\d{9}(?!\d)")
KEYED_ID_RE = re.compile(r"(?i)\b(uid|account_id|accountid|user_id|userid)\b(\s*[:=：]?\s*)\d{4,}")
LONG_DIGIT_RE = re.compile(r"(?<!\d)\d{8,12}(?!\d)")
JSON_KEY_RE = re.compile(r'"([^"\\]*(?:\\.[^"\\]*)*)"\s*:')


class ProbeError(RuntimeError):
    pass


def redact_text(value: Any) -> str:
    text = "" if value is None else str(value)
    text = SECRET_VALUE_RE.sub(lambda m: f"{m.group(1)}{m.group(2)}[REDACTED_SECRET]", text)
    text = BEARER_RE.sub(r"\1[REDACTED_SECRET]", text)
    text = EMAIL_RE.sub("[REDACTED_EMAIL]", text)
    text = PHONE_RE.sub("[REDACTED_PHONE]", text)
    text = KEYED_ID_RE.sub(lambda m: f"{m.group(1)}{m.group(2)}[REDACTED_ID]", text)
    text = LONG_DIGIT_RE.sub("[REDACTED_ID]", text)
    return text


def redact_path(path: Path | str) -> str:
    return redact_text(str(path).replace("\\", "/"))


def truncate(text: str, limit: int = 160) -> str:
    clean = text.replace("\r", " ").replace("\n", " ").strip()
    if len(clean) <= limit:
        return clean
    return clean[: limit - 3] + "..."


def markdown_cell(value: Any, limit: int = 80) -> str:
    return truncate(redact_text(value), limit).replace("|", "\\|")


def now_iso() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def output_stem() -> str:
    return datetime.now().strftime("miyoushe_local_inventory_%Y%m%d_%H%M%S")


def is_sensitive_path(relative_path: Path) -> bool:
    haystack = "/".join(relative_path.parts)
    return bool(SENSITIVE_PATH_RE.search(haystack))


def file_mtime(path: Path) -> str:
    return datetime.fromtimestamp(path.stat().st_mtime).astimezone().isoformat(timespec="seconds")


def read_header(path: Path, byte_count: int = 64) -> bytes:
    with path.open("rb") as handle:
        return handle.read(byte_count)


def detect_file_type(path: Path, header: bytes) -> str:
    ext = path.suffix.lower()
    if header.startswith(b"SQLite format 3\x00"):
        return "sqlite"
    if ext in SQLITE_EXTENSIONS:
        return "sqlite_candidate"
    if ext == ".json":
        return "json"
    if ext in {".html", ".htm"}:
        return "html"
    if ext == ".log":
        return "log"
    if ext == ".txt":
        return "text"
    if header.startswith(b"\x1f\x8b"):
        return "gzip"
    if header.startswith(b"PK\x03\x04"):
        return "zip"
    if b"\x00" in header:
        return "binary"
    if ext:
        return f"unknown{ext}"
    return "unknown"


def decode_sample(data: bytes) -> str:
    for encoding in ("utf-8-sig", "utf-8", "gb18030"):
        try:
            return data.decode(encoding)
        except UnicodeDecodeError:
            continue
    return data.decode("utf-8", errors="replace")


def extract_json_keys(sample_text: str, limit: int = 80) -> list[str]:
    keys: list[str] = []
    seen: set[str] = set()
    for match in JSON_KEY_RE.finditer(sample_text):
        key = redact_text(match.group(1))
        if key and key not in seen:
            seen.add(key)
            keys.append(key)
        if len(keys) >= limit:
            break
    return keys


def text_probe(path: Path, sample_bytes: int) -> dict[str, Any]:
    with path.open("rb") as handle:
        sample_data = handle.read(sample_bytes)
    decoded = decode_sample(sample_data)
    redacted = redact_text(decoded)
    return {
        "sample_bytes_read": len(sample_data),
        "sample_preview": truncate(redacted, 500),
        "json_key_sample": extract_json_keys(redacted),
    }


def quote_sql_identifier(identifier: str) -> str:
    return '"' + identifier.replace('"', '""') + '"'


def sqlite_probe(path: Path) -> dict[str, Any]:
    objects: list[dict[str, Any]] = []
    table_columns: dict[str, list[str]] = {}
    uri = f"file:{path.as_posix()}?mode=ro"

    connection = sqlite3.connect(uri, uri=True)
    try:
        cursor = connection.execute(
            "select type, name, tbl_name, sql from sqlite_master "
            "where type in ('table', 'view', 'index', 'trigger') "
            "order by type, name limit 200"
        )
        for obj_type, name, tbl_name, sql in cursor.fetchall():
            name_text = redact_text(name)
            objects.append(
                {
                    "type": redact_text(obj_type),
                    "name": name_text,
                    "table": redact_text(tbl_name),
                    "sql_summary": truncate(redact_text(sql or ""), 220),
                }
            )
            if obj_type == "table" and name and not str(name).startswith("sqlite_"):
                try:
                    column_cursor = connection.execute(f"pragma table_info({quote_sql_identifier(str(name))})")
                    table_columns[name_text] = [redact_text(row[1]) for row in column_cursor.fetchall()]
                except sqlite3.Error:
                    table_columns[name_text] = []
    finally:
        connection.close()

    return {
        "object_count": len(objects),
        "objects": objects,
        "table_columns": table_columns,
    }


def iter_files(root: Path, max_depth: int, max_files: int):
    count = 0
    for current_root, dirs, files in os.walk(root, topdown=True, followlinks=False):
        current = Path(current_root)
        try:
            relative_dir = current.relative_to(root)
        except ValueError:
            continue
        depth = 0 if str(relative_dir) == "." else len(relative_dir.parts)
        dirs[:] = sorted(d for d in dirs if not d.startswith("."))
        files = sorted(files)

        if depth >= max_depth:
            dirs[:] = []

        for filename in files:
            if count >= max_files:
                return
            path = current / filename
            if path.is_symlink() or not path.is_file():
                continue
            yield path
            count += 1


def inspect_file(root: Path, path: Path, sample_bytes: int) -> dict[str, Any]:
    relative_path = path.relative_to(root)
    stat = path.stat()
    header = read_header(path)
    file_type = detect_file_type(path, header)
    sensitive = is_sensitive_path(relative_path)
    entry: dict[str, Any] = {
        "relative_path": redact_path(relative_path),
        "extension": path.suffix.lower(),
        "size_bytes": stat.st_size,
        "mtime": file_mtime(path),
        "file_type": file_type,
        "file_header_hex": header[:16].hex(),
        "sensitive_suspected": sensitive,
        "notes": [],
    }

    if sensitive:
        entry["notes"].append("Sensitive-looking path. Content was not read.")
        return entry

    try:
        if path.suffix.lower() in TEXT_EXTENSIONS:
            entry["text_probe"] = text_probe(path, sample_bytes)
        elif file_type in {"sqlite", "sqlite_candidate"}:
            entry["sqlite_probe"] = sqlite_probe(path)
    except (OSError, UnicodeError, sqlite3.Error) as exc:
        entry["notes"].append(redact_text(f"Probe failed: {exc}"))

    return entry


def build_summary(files: list[dict[str, Any]], truncated_by_limit: bool) -> dict[str, Any]:
    type_counts = Counter(item.get("file_type", "unknown") for item in files)
    extension_counts = Counter(item.get("extension", "") or "[none]" for item in files)
    sensitive_count = sum(1 for item in files if item.get("sensitive_suspected"))
    json_candidates = [
        item
        for item in files
        if item.get("file_type") == "json" or item.get("extension") == ".json"
    ]
    sqlite_candidates = [
        item
        for item in files
        if item.get("file_type") in {"sqlite", "sqlite_candidate"} or item.get("extension") in SQLITE_EXTENSIONS
    ]
    html_candidates = [
        item
        for item in files
        if item.get("file_type") == "html" or item.get("extension") in {".html", ".htm"}
    ]
    return {
        "file_count": len(files),
        "truncated_by_limit": truncated_by_limit,
        "sensitive_suspected_count": sensitive_count,
        "file_type_counts": dict(type_counts),
        "extension_counts": dict(extension_counts),
        "json_candidate_count": len(json_candidates),
        "sqlite_candidate_count": len(sqlite_candidates),
        "html_candidate_count": len(html_candidates),
    }


def run_inventory(root: Path, max_depth: int, max_files: int, sample_bytes: int) -> dict[str, Any]:
    if not root.exists():
        raise ProbeError(f"Root does not exist: {root}")
    if not root.is_dir():
        raise ProbeError(f"Root is not a directory: {root}")

    files: list[dict[str, Any]] = []
    for path in iter_files(root, max_depth=max_depth, max_files=max_files):
        files.append(inspect_file(root, path, sample_bytes))

    # Detect whether the walker stopped because of the max file limit.
    observed_count = 0
    for _ in iter_files(root, max_depth=max_depth, max_files=max_files + 1):
        observed_count += 1
        if observed_count > max_files:
            break
    truncated_by_limit = observed_count > max_files

    return {
        "metadata": {
            "probe": "miyoushe_local_inventory",
            "created_at": now_iso(),
            "root": "[USER_SPECIFIED_ROOT_REDACTED]",
            "root_name": redact_text(root.name),
            "max_depth": max_depth,
            "max_files": max_files,
            "sample_bytes": sample_bytes,
            "notes": [
                "Read-only local inventory.",
                "Root must be explicitly provided by the user.",
                "No automatic APP profile guessing, uploads, token reads, packet capture, or SQLite writes.",
            ],
        },
        "summary": build_summary(files, truncated_by_limit),
        "files": files,
    }


def write_outputs(result: dict[str, Any]) -> tuple[Path, Path]:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    stem = output_stem()
    json_path = OUTPUT_DIR / f"{stem}.json"
    md_path = OUTPUT_DIR / f"{stem}.md"
    json_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    md_path.write_text(render_markdown(result), encoding="utf-8")
    return json_path, md_path


def render_markdown(result: dict[str, Any]) -> str:
    meta = result["metadata"]
    summary = result["summary"]
    files = result["files"]
    lines = [
        "# 米游社本地数据 Inventory",
        "",
        "## 摘要",
        "",
        f"- 创建时间：{markdown_cell(meta.get('created_at'), 120)}",
        f"- 根目录：{markdown_cell(meta.get('root'), 120)}",
        f"- 根目录名称：{markdown_cell(meta.get('root_name'), 120)}",
        f"- 文件数量：{summary.get('file_count')}",
        f"- 疑似敏感文件数量：{summary.get('sensitive_suspected_count')}",
        f"- JSON 候选：{summary.get('json_candidate_count')}",
        f"- SQLite 候选：{summary.get('sqlite_candidate_count')}",
        f"- HTML 候选：{summary.get('html_candidate_count')}",
        f"- 是否触达文件数上限：{summary.get('truncated_by_limit')}",
        "",
        "## 限制",
        "",
        "- 本工具只扫描用户显式传入的目录。",
        "- 疑似 cookie/token/session/storage/login/auth 文件只记录存在，不读取内容。",
        "- SQLite 只读取表名和 schema 摘要，不读取表数据。",
        "- 本文件不得提交 Git。",
        "",
        "## 文件类型统计",
        "",
    ]

    for file_type, count in sorted(summary.get("file_type_counts", {}).items()):
        lines.append(f"- {markdown_cell(file_type)}: {count}")
    lines.append("")

    sensitive_files = [item for item in files if item.get("sensitive_suspected")]
    if sensitive_files:
        lines.extend(["## 疑似敏感文件", ""])
        for item in sensitive_files[:100]:
            lines.append(f"- {markdown_cell(item.get('relative_path'), 160)} ({markdown_cell(item.get('file_type'))})")
        if len(sensitive_files) > 100:
            lines.append(f"- ... 还有 {len(sensitive_files) - 100} 个")
        lines.append("")

    json_files = [item for item in files if item.get("text_probe", {}).get("json_key_sample")]
    if json_files:
        lines.extend(["## JSON / 文本 key 样本", ""])
        for item in json_files[:50]:
            keys = ", ".join(item["text_probe"].get("json_key_sample", [])[:30])
            lines.append(f"- {markdown_cell(item.get('relative_path'), 140)}: {markdown_cell(keys, 240)}")
        lines.append("")

    sqlite_files = [item for item in files if item.get("sqlite_probe")]
    if sqlite_files:
        lines.extend(["## SQLite schema 摘要", ""])
        for item in sqlite_files[:50]:
            objects = item["sqlite_probe"].get("objects", [])
            names = ", ".join(obj.get("name", "") for obj in objects[:30])
            lines.append(f"- {markdown_cell(item.get('relative_path'), 140)}: {markdown_cell(names, 240)}")
        lines.append("")

    lines.extend(
        [
            "## 文件列表",
            "",
            "| path | ext | size | mtime | type | sensitive | notes |",
            "|---|---|---:|---|---|---|---|",
        ]
    )
    for item in files[:500]:
        notes = "; ".join(item.get("notes", []))
        lines.append(
            "| "
            f"{markdown_cell(item.get('relative_path'), 140)} | "
            f"{markdown_cell(item.get('extension'))} | "
            f"{item.get('size_bytes')} | "
            f"{markdown_cell(item.get('mtime'), 80)} | "
            f"{markdown_cell(item.get('file_type'))} | "
            f"{item.get('sensitive_suspected')} | "
            f"{markdown_cell(notes, 120)} |"
        )
    if len(files) > 500:
        lines.append(f"| ... | ... | ... | ... | ... | ... | 还有 {len(files) - 500} 个文件 |")
    lines.append("")
    return "\n".join(lines)


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Read-only inventory of a user-specified MiYouShe app data directory. "
            "No automatic profile guessing, token reads, uploads, packet capture, or SQLite writes."
        )
    )
    parser.add_argument("--root", required=True, help="User-specified local directory to scan.")
    parser.add_argument("--max-depth", type=int, default=4, help="Maximum directory depth below --root. Default: 4")
    parser.add_argument("--max-files", type=int, default=500, help="Maximum files to inspect. Default: 500")
    parser.add_argument("--sample-bytes", type=int, default=4096, help="Header sample size for text files. Default: 4096")
    return parser


def main() -> int:
    args = build_arg_parser().parse_args()
    root = Path(args.root).expanduser().resolve()
    max_depth = max(0, min(args.max_depth, 12))
    max_files = max(1, args.max_files)
    sample_bytes = max(128, min(args.sample_bytes, 16384))

    try:
        result = run_inventory(root, max_depth=max_depth, max_files=max_files, sample_bytes=sample_bytes)
        json_path, md_path = write_outputs(result)
        print(f"Wrote JSON: {json_path}")
        print(f"Wrote Markdown: {md_path}")
        return 0
    except ProbeError as exc:
        print(f"ERROR: {redact_text(exc)}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
