from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from hsr_endgame_exporter.normalize import normalize_character_id


@dataclass
class OwnedAgent:
    slug: str
    name_cn: str = ""
    owned: bool = True
    cinema: int = 0
    signature: int = 0
    level: int | None = None
    w_engine_level: int | None = None
    core_skill: int | None = None
    drive_discs: str = ""
    notes: str = ""
    raw: dict[str, Any] = field(default_factory=dict)

    @property
    def stage(self) -> str:
        return f"{self.cinema}+{self.signature}"


@dataclass
class BoxProfile:
    agents: dict[str, OwnedAgent] = field(default_factory=dict)
    account: dict[str, Any] = field(default_factory=dict)
    goals: dict[str, Any] = field(default_factory=dict)

    def owned(self, slug: str | None) -> OwnedAgent | None:
        return self.agents.get(normalize_character_id(slug))

    def has(self, slug: str | None) -> bool:
        agent = self.owned(slug)
        return bool(agent and agent.owned)


def load_box(path: str | Path) -> BoxProfile:
    data = load_config(path)
    agents: dict[str, OwnedAgent] = {}
    for row in _agent_rows(data.get("agents")):
        slug = normalize_character_id(row.get("slug") or row.get("id") or row.get("name_en") or row.get("name"))
        if not slug:
            continue
        owned = _bool(row.get("owned", True))
        agent = OwnedAgent(
            slug=slug,
            name_cn=str(row.get("name_cn") or row.get("name") or ""),
            owned=owned,
            cinema=_int(row.get("cinema", row.get("mindscape", row.get("copies", 0))), 0),
            signature=_int(row.get("signature", row.get("w_engine_signature", 0)), 0),
            level=_optional_int(row.get("level")),
            w_engine_level=_optional_int(row.get("w_engine_level", row.get("weapon_level"))),
            core_skill=_optional_int(row.get("core_skill")),
            drive_discs=str(row.get("drive_discs") or row.get("discs") or ""),
            notes=str(row.get("notes") or ""),
            raw=dict(row),
        )
        agents[slug] = agent
    return BoxProfile(
        agents=agents,
        account=dict(data.get("account") or {}),
        goals=dict(data.get("goals") or {}),
    )


def load_config(path: str | Path) -> dict[str, Any]:
    config_path = Path(path)
    if not config_path.exists():
        raise FileNotFoundError(f"配置文件不存在：{config_path}")
    text = config_path.read_text(encoding="utf-8-sig")
    stripped = text.lstrip()
    if stripped.startswith("{"):
        value = json.loads(text)
    else:
        value = _load_yaml(text)
    if not isinstance(value, dict):
        raise ValueError(f"配置文件必须是 mapping：{config_path}")
    return value


def _load_yaml(text: str) -> Any:
    try:
        import yaml  # type: ignore
    except ImportError as error:
        raise RuntimeError("PyYAML is required to read YAML configuration") from error
    return yaml.safe_load(text) or {}


def _load_simple_yaml(text: str) -> dict[str, Any]:
    root: dict[str, Any] = {}
    current_key: str | None = None
    current_item: dict[str, Any] | None = None
    current_map: dict[str, Any] | None = None

    for raw_line in text.splitlines():
        line = raw_line.split("#", 1)[0].rstrip()
        if not line.strip():
            continue
        indent = len(line) - len(line.lstrip(" "))
        stripped = line.strip()
        if indent == 0 and stripped.endswith(":"):
            current_key = stripped[:-1].strip()
            root[current_key] = []
            current_item = None
            current_map = None
            continue
        if indent == 0 and ":" in stripped:
            key, value = stripped.split(":", 1)
            root[key.strip()] = _parse_scalar(value.strip())
            current_key = None
            current_item = None
            current_map = None
            continue
        if current_key is None:
            continue
        if stripped.startswith("- "):
            if not isinstance(root.get(current_key), list):
                root[current_key] = []
            current_item = {}
            current_map = current_item
            root[current_key].append(current_item)
            remainder = stripped[2:].strip()
            if remainder and ":" in remainder:
                key, value = remainder.split(":", 1)
                current_item[key.strip()] = _parse_scalar(value.strip())
            continue
        if ":" not in stripped:
            continue
        key, value = stripped.split(":", 1)
        target: dict[str, Any]
        if current_item is not None and indent >= 4:
            target = current_item
        else:
            if isinstance(root.get(current_key), list):
                root[current_key] = {}
            current_map = root[current_key]
            target = current_map if isinstance(current_map, dict) else root
        target[key.strip()] = _parse_scalar(value.strip())
    return root


def _parse_scalar(value: str) -> Any:
    text = value.strip()
    if text == "":
        return ""
    if (text.startswith('"') and text.endswith('"')) or (text.startswith("'") and text.endswith("'")):
        return text[1:-1]
    if text.startswith("[") and text.endswith("]"):
        inner = text[1:-1].strip()
        if not inner:
            return []
        return [_parse_scalar(part.strip()) for part in inner.split(",")]
    lowered = text.lower()
    if lowered in {"true", "yes", "y"}:
        return True
    if lowered in {"false", "no", "n"}:
        return False
    if lowered in {"null", "none", "~"}:
        return None
    try:
        return int(text)
    except ValueError:
        pass
    try:
        return float(text)
    except ValueError:
        return text


def _agent_rows(value: Any) -> list[dict[str, Any]]:
    if isinstance(value, list):
        return [dict(item) for item in value if isinstance(item, dict)]
    if isinstance(value, dict):
        rows: list[dict[str, Any]] = []
        for slug, item in value.items():
            if isinstance(item, dict):
                rows.append({"slug": slug, **item})
            else:
                rows.append({"slug": slug, "owned": _bool(item)})
        return rows
    return []


def _bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() not in {"0", "false", "no", "n", "未拥有"}


def _int(value: Any, default: int) -> int:
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return default


def _optional_int(value: Any) -> int | None:
    if value in {None, ""}:
        return None
    return _int(value, 0)

