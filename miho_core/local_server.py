from __future__ import annotations

import argparse
import json
import mimetypes
from http import HTTPStatus
from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler
from pathlib import Path
from typing import Any


BOX_STATE_PATHS = {
    "hsr": Path(".miho") / "hsr_box_state.json",
    "zzz": Path(".miho") / "zzz_box_state.json",
}


class MihoRequestHandler(SimpleHTTPRequestHandler):
    def do_GET(self) -> None:  # noqa: N802
        game = _box_game_from_path(self.path)
        if game:
            self._send_json(_read_box_state(game))
            return
        super().do_GET()

    def do_POST(self) -> None:  # noqa: N802
        game = _box_game_from_path(self.path)
        if game:
            self._save_box_state(game)
            return
        self.send_error(HTTPStatus.NOT_FOUND)

    def do_PUT(self) -> None:  # noqa: N802
        self.do_POST()

    def end_headers(self) -> None:
        self.send_header("Cache-Control", "no-store")
        super().end_headers()

    def _save_box_state(self, game: str) -> None:
        try:
            length = int(self.headers.get("Content-Length") or 0)
            body = self.rfile.read(length).decode("utf-8")
            payload = json.loads(body or "{}")
            state = _normalize_box_state(payload)
            _write_box_state(game, state)
        except Exception as exc:  # pragma: no cover - request boundary
            self._send_json({"ok": False, "error": str(exc)}, status=HTTPStatus.BAD_REQUEST)
            return
        self._send_json({"ok": True, "state": state})

    def _send_json(self, payload: dict[str, Any], status: int = HTTPStatus.OK) -> None:
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)


def run_server(root: str | Path = ".", host: str = "127.0.0.1", port: int = 8765) -> None:
    directory = Path(root).resolve()
    mimetypes.add_type("application/javascript; charset=utf-8", ".js")
    handler = lambda *args, **kwargs: MihoRequestHandler(*args, directory=str(directory), **kwargs)
    server = ThreadingHTTPServer((host, port), handler)
    print(f"Miho visualizer server: http://{host}:{port}/visualizer/index.html")
    server.serve_forever()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m miho_core.local_server")
    parser.add_argument("--root", default=".")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args(argv)
    run_server(args.root, args.host, args.port)
    return 0


def _box_game_from_path(path: str) -> str:
    request_path = path.split("?", 1)[0]
    for game in BOX_STATE_PATHS:
        if request_path == f"/api/{game}/box":
            return game
    return ""


def _empty_box_state() -> dict[str, Any]:
    return {"version": 2, "updatedAt": "", "owned": [], "buildSlug": "", "builds": {}}


def _read_box_state(game: str) -> dict[str, Any]:
    path = BOX_STATE_PATHS[game]
    if not path.exists():
        return _empty_box_state()
    try:
        return _normalize_box_state(json.loads(path.read_text(encoding="utf-8")))
    except json.JSONDecodeError:
        return {**_empty_box_state(), "warning": "box state file is invalid"}


def _write_box_state(game: str, state: dict[str, Any]) -> None:
    path = BOX_STATE_PATHS[game]
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.with_suffix(".tmp")
    temp_path.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
    temp_path.replace(path)


def _normalize_box_state(payload: dict[str, Any]) -> dict[str, Any]:
    owned = sorted(
        {
            str(item).strip()
            for item in payload.get("owned") or []
            if str(item).strip() and str(item).strip() != "__codex_test__"
        }
    )
    builds = payload.get("builds") if isinstance(payload.get("builds"), dict) else {}
    build_slug = str(payload.get("buildSlug") or "")
    updated_at = str(payload.get("updatedAt") or payload.get("exportedAt") or "")
    if not owned and not builds and not build_slug:
        updated_at = ""
    return {
        "version": 2,
        "updatedAt": updated_at,
        "owned": owned,
        "buildSlug": build_slug,
        "builds": builds,
    }


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
