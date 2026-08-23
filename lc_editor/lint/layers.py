from __future__ import annotations

from lc_editor.models import LEGAL_EFFECTS, LayerItem, MediaItem, Timeline
from lc_editor.ops.layers import layer_off_canvas


def layer_issues(timeline: Timeline, media: list[MediaItem] | None = None) -> list[str]:
    errors: list[str] = []
    known = {item.id for item in (media or [])}
    for layer in timeline.layers:
        if layer.duration_s <= 0:
            errors.append(f"SPEC-LAY-05: layer {layer.id} has no duration")
        if layer.kind == "text":
            if not layer.text.strip():
                errors.append(f"SPEC-LAY-05: text layer {layer.id} is empty")
            if "box=1" in (layer.textfile or ""):
                errors.append(f"SPEC-CRAFT-02: layer {layer.id} has a caption box")
        elif not layer.media_id:
            errors.append(f"SPEC-LAY-05: layer {layer.id} is missing media")
        elif media is not None and layer.media_id not in known:
            errors.append(f"SPEC-LAY-05: layer {layer.id} references missing media {layer.media_id}")
        if layer_off_canvas(layer):
            errors.append(f"SPEC-LAY-05: layer {layer.id} is off-canvas")
        for effect in layer.effects:
            if effect.name not in LEGAL_EFFECTS:
                errors.append(f"SPEC-RND-16: layer {layer.id} has unknown effect {effect.name}")
    for clip in timeline.clips:
        for effect in clip.effects:
            if effect.name not in LEGAL_EFFECTS:
                errors.append(f"SPEC-RND-16: clip {clip.id} has unknown effect {effect.name}")
    return errors
