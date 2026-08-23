from __future__ import annotations

import json
from typing import Any

from lc_editor.models import (
    LAYOUT_PANE_COUNT,
    LEGAL_LAYOUTS,
    SHOT_ACK_MIN_S,
    STILL_ACK_MIN_S,
    Clip,
    LayoutPane,
    MediaItem,
    Timeline,
)
from lc_editor.ops.timeline import Reject, add_clip


def parse_panes(raw: list[dict] | str | None) -> list[LayoutPane]:
    if raw is None:
        raise Reject("SPEC-LAYO-01: panes required")
    payload: Any = raw
    if isinstance(raw, str):
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise Reject("SPEC-LAYO-01: panes must be a list of objects") from exc
    if not isinstance(payload, list) or not payload:
        raise Reject("SPEC-LAYO-01: panes must be a non-empty list")
    panes: list[LayoutPane] = []
    for i, item in enumerate(payload):
        if not isinstance(item, dict):
            raise Reject(f"SPEC-LAYO-01: pane {i} must be an object")
        media_id = item.get("media_id")
        if not media_id:
            raise Reject(f"SPEC-LAYO-01: pane {i} needs media_id")
        in_s = float(item.get("in_s") or 0.0)
        if in_s < 0:
            raise Reject(f"SPEC-LAYO-01: pane {i} in_s must be >= 0")
        focus_x = float(item.get("focus_x", 0.5))
        focus_y = float(item.get("focus_y", 0.5))
        if not (0.0 <= focus_x <= 1.0 and 0.0 <= focus_y <= 1.0):
            raise Reject(f"SPEC-LAYO-01: pane {i} focus must be in [0, 1]")
        panes.append(LayoutPane(media_id=str(media_id), in_s=round(in_s, 4), focus_x=focus_x, focus_y=focus_y))
    return panes


def validate_layout(kind: str, panes: list[LayoutPane]) -> str:
    if kind not in LEGAL_LAYOUTS:
        raise Reject(f"SPEC-LAYO-01: unknown layout {kind}")
    need = LAYOUT_PANE_COUNT[kind]
    if len(panes) != need:
        raise Reject(f"SPEC-LAYO-01: {kind} needs {need} panes, got {len(panes)}")
    return kind


def resolve_layout_duration(
    panes: list[LayoutPane],
    items: list[MediaItem],
    duration_s: float | None,
) -> float:
    floors: list[float] = []
    avails: list[float] = []
    for pane, item in zip(panes, items, strict=True):
        if item.kind == "audio":
            raise Reject("SPEC-LAYO-01: audio files are not layout panes")
        if item.kind == "image":
            floors.append(STILL_ACK_MIN_S)
            avails.append(10.0)
            continue
        remain = max(0.01, (item.duration_s or 0.0) - pane.in_s)
        floors.append(min(SHOT_ACK_MIN_S, remain))
        avails.append(remain)
    if duration_s is not None:
        if duration_s <= 0:
            raise Reject("SPEC-LAYO-01: duration must be positive")
        return round(duration_s, 4)
    return round(min(max(floors), min(avails)), 4)


def all_panes_still(items: list[MediaItem]) -> bool:
    return all(item.kind == "image" for item in items)


def build_layout_clip(
    clip_id: str,
    kind: str,
    panes: list[LayoutPane],
    items: list[MediaItem],
    duration_s: float,
) -> Clip:
    validate_layout(kind, panes)
    stills = all_panes_still(items)
    dur = duration_s
    return Clip(
        id=clip_id,
        media_id=panes[0].media_id,
        in_s=panes[0].in_s,
        out_s=round(panes[0].in_s + dur, 4),
        duration_s=round(dur, 4),
        focus_x=panes[0].focus_x,
        focus_y=panes[0].focus_y,
        motion="kenburns" if stills else "none",
        is_still=stills,
        layout=kind,  # type: ignore[arg-type]
        panes=panes,
    )


def add_layout(timeline: Timeline, clip: Clip) -> Timeline:
    if not clip.layout:
        raise Reject("SPEC-LAYO-01: clip is not a layout")
    validate_layout(clip.layout, clip.panes)
    return add_clip(timeline, clip)


def update_layout(
    timeline: Timeline,
    clip_id: str,
    kind: str | None = None,
    panes: list[LayoutPane] | None = None,
) -> Timeline:
    i = _clip_index(timeline, clip_id)
    clip = timeline.clips[i]
    if not clip.layout:
        raise Reject("SPEC-LAYO-03: clip is not a layout")
    next_kind = kind or clip.layout
    next_panes = panes if panes is not None else list(clip.panes)
    validate_layout(next_kind, next_panes)
    update: dict = {"layout": next_kind, "panes": next_panes}
    update.update(_primary_fields(next_panes[0], clip.duration_s))
    clips = list(timeline.clips)
    clips[i] = clip.model_copy(update=update)
    return timeline.model_copy(update={"clips": clips})


def set_layout_pane(timeline: Timeline, clip_id: str, index: int, pane: LayoutPane, duration_s: float) -> Timeline:
    i = _clip_index(timeline, clip_id)
    clip = timeline.clips[i]
    if not clip.layout:
        raise Reject("SPEC-LAYO-03: clip is not a layout")
    if index < 0 or index >= len(clip.panes):
        raise Reject(f"SPEC-LAYO-03: pane index {index} is out of range")
    panes = list(clip.panes)
    panes[index] = pane
    validate_layout(clip.layout, panes)
    update: dict = {"panes": panes}
    if index == 0:
        update.update(_primary_fields(pane, duration_s))
    clips = list(timeline.clips)
    clips[i] = clip.model_copy(update=update)
    return timeline.model_copy(update={"clips": clips})


def clear_layout(timeline: Timeline, clip_id: str) -> Timeline:
    i = _clip_index(timeline, clip_id)
    clip = timeline.clips[i]
    if not clip.layout:
        raise Reject("SPEC-LAYO-04: clip is not a layout")
    clips = list(timeline.clips)
    clips[i] = clip.model_copy(update={"layout": None, "panes": []})
    return timeline.model_copy(update={"clips": clips})


def sync_primary_pane(clip: Clip, **fields) -> Clip:
    update = dict(fields)
    if clip.layout and clip.panes:
        pane_fields = {k: v for k, v in fields.items() if k in ("media_id", "in_s", "focus_x", "focus_y")}
        if pane_fields:
            pane0 = clip.panes[0].model_copy(update=pane_fields)
            update["panes"] = [pane0, *clip.panes[1:]]
    return clip.model_copy(update=update)


def _primary_fields(pane: LayoutPane, duration_s: float) -> dict:
    return {
        "media_id": pane.media_id,
        "in_s": pane.in_s,
        "out_s": round(pane.in_s + duration_s, 4),
        "focus_x": pane.focus_x,
        "focus_y": pane.focus_y,
    }


def _clip_index(timeline: Timeline, clip_id: str) -> int:
    for i, clip in enumerate(timeline.clips):
        if clip.id == clip_id:
            return i
    raise Reject(f"unknown clip {clip_id}")
