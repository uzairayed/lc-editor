from __future__ import annotations

import json
from pathlib import Path

from lc_editor.models import DURATION_CAP_MAX_S, MIN_VIDEO_DURATION_S

PRESET_DIR = Path(__file__).resolve().parent

# Project presets exposed on MCP create/set (templates like editorial stay template_apply).
PROJECT_PRESET_NAMES = ("karachi", "process")


def list_presets() -> list[str]:
    return sorted(p.stem for p in PRESET_DIR.glob("*.json"))


def load_preset(name: str) -> dict:
    path = PRESET_DIR / f"{name}.json"
    if not path.exists():
        raise KeyError(name)
    return json.loads(path.read_text(encoding="utf-8"))


def project_fields_from_preset(data: dict) -> dict:
    """Map preset JSON onto Project update fields.

    Never sets ``allow_music`` true (SPEC-CRAFT-01 / SPEC-SES-12).
    """
    update: dict = {}
    grade = data.get("grade")
    if grade in ("motovlog", "winter_trip", "neutral"):
        update["grade_preset"] = grade
    if "duration_cap_s" in data:
        try:
            cap = float(data["duration_cap_s"])
        except (TypeError, ValueError):
            cap = -1.0
        if 0 < cap <= DURATION_CAP_MAX_S:
            update["duration_cap_s"] = cap
    contrast = data.get("caption_contrast")
    if contrast in ("strict", "lenient"):
        update["caption_contrast"] = contrast
    if "min_video_duration_s" in data:
        try:
            floor = float(data["min_video_duration_s"])
        except (TypeError, ValueError):
            floor = -1.0
        if floor >= 0:
            update["min_video_duration_s"] = MIN_VIDEO_DURATION_S if floor == 0 else floor
    loudnorm = data.get("loudnorm")
    if loudnorm in ("cinema", "speech"):
        update["loudnorm"] = loudnorm
    if data.get("allow_music") is False:
        update["allow_music"] = False
    return update
