from __future__ import annotations

from lc_editor.models import (
    SCHEMA_V2,
    BeatGrid,
    Caption,
    LayerItem,
    TextStyle,
    Timeline,
)


def caption_to_layer(caption: Caption, start_s: float, duration_s: float) -> LayerItem:
    motion = "pop" if caption.enter == "punch" else caption.enter
    if motion not in ("none", "fade", "pop", "slide", "type_on"):
        motion = "fade"
    return LayerItem(
        id=f"ly_{caption.id}",
        kind="text",
        z=20,
        start_s=start_s,
        duration_s=duration_s,
        text=caption.text,
        role=caption.role,
        clip_id=caption.clip_id,
        caption_id=caption.id,
        y_pct=caption.y_pct,
        lines=list(caption.lines),
        hold_s=caption.hold_s,
        textfile=caption.textfile,
        style=TextStyle(role=caption.role, motion=motion),  # type: ignore[arg-type]
    )


def sync_caption_layers(timeline: Timeline) -> Timeline:
    clips = {c.id: c for c in timeline.clips}
    bound = {layer.caption_id: layer for layer in timeline.layers if layer.caption_id}
    kept = [layer for layer in timeline.layers if not layer.caption_id]
    for cap in timeline.captions:
        clip = clips.get(cap.clip_id)
        start = clip.start_s if clip else 0.0
        dur = min(cap.hold_s, clip.duration_s) if clip else cap.hold_s
        existing = bound.get(cap.id)
        layer = caption_to_layer(cap, start, dur)
        if existing:
            layer = layer.model_copy(
                update={
                    "id": existing.id,
                    "z": existing.z,
                    "transform": existing.transform,
                    "keyframes": existing.keyframes,
                    "effects": existing.effects,
                    "style": existing.style.model_copy(update={"role": cap.role}),
                }
            )
        kept.append(layer)
    return timeline.model_copy(update={"layers": kept, "schema_version": SCHEMA_V2})


def migrate_timeline_data(data: dict) -> Timeline:
    payload = dict(data)
    version = int(payload.get("schema_version") or 1)
    payload.setdefault("layers", [])
    payload.setdefault("music", [])
    payload.setdefault("beat_grid", None)
    payload.setdefault("template_id", None)
    payload["schema_version"] = SCHEMA_V2
    timeline = Timeline.model_validate(payload)
    if version < SCHEMA_V2 or (timeline.captions and not any(layer.caption_id for layer in timeline.layers)):
        timeline = sync_caption_layers(timeline)
    if payload.get("beat_grid") and not isinstance(timeline.beat_grid, BeatGrid | type(None)):
        timeline = timeline.model_copy(update={"beat_grid": BeatGrid.model_validate(payload["beat_grid"])})
    return timeline
