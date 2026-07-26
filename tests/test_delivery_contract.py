from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_default_tauri_build_keeps_desktop_and_update_cli_in_sync() -> None:
    package = json.loads((ROOT / "package.json").read_text(encoding="utf-8"))
    script = package["scripts"]["tauri:build"]
    cli_build = "cargo build --locked --release -p miho-cli"
    desktop_build = (
        "cargo build --locked --release -p miho-desktop --features custom-protocol"
    )
    embedded_visualizer_gate = (
        "node scripts/verify_embedded_visualizer_bytes_v1.mjs"
    )

    assert script.count(cli_build) == 1
    assert script.count(desktop_build) == 1
    assert script.count(embedded_visualizer_gate) == 1
    assert (
        script.index(cli_build)
        < script.index(desktop_build)
        < script.index(embedded_visualizer_gate)
    )
    assert script.endswith(embedded_visualizer_gate)
