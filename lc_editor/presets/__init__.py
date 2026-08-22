from __future__ import annotations

import json
from pathlib import Path

PRESET_DIR = Path(__file__).resolve().parent


def list_presets() -> list[str]:
    return sorted(p.stem for p in PRESET_DIR.glob("*.json"))


def load_preset(name: str) -> dict:
    path = PRESET_DIR / f"{name}.json"
    if not path.exists():
        raise KeyError(name)
    return json.loads(path.read_text(encoding="utf-8"))
