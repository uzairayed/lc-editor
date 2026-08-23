from __future__ import annotations

from lc_editor.models import (
    CANVAS_H,
    CANVAS_W,
    LEGAL_EFFECTS,
    EffectInstance,
    Keyframe,
    LayerItem,
    Timeline,
    Transform,
)
from lc_editor.ops.timeline import Reject


def _layer_index(timeline: Timeline, layer_id: str) -> int:
    for i, layer in enumerate(timeline.layers):
        if layer.id == layer_id:
            return i
    raise Reject(f"unknown layer {layer_id}")


def add_layer(timeline: Timeline, layer: LayerItem) -> Timeline:
    if layer.duration_s <= 0:
        raise Reject("SPEC-LAY-05: duration must be positive")
    if layer.kind == "text":
        if not layer.text.strip():
            raise Reject("SPEC-LAY-01: text layer needs text")
    elif not layer.media_id:
        raise Reject("SPEC-LAY-01: media layer needs media_id")
    return timeline.model_copy(update={"layers": [*timeline.layers, layer]})


def update_layer(timeline: Timeline, layer_id: str, **fields) -> Timeline:
    i = _layer_index(timeline, layer_id)
    layers = list(timeline.layers)
    allowed = {
        "start_s",
        "duration_s",
        "z",
        "text",
        "y_pct",
        "role",
        "media_id",
        "in_s",
        "hold_s",
        "lines",
    }
    update = {k: v for k, v in fields.items() if v is not None and k in allowed}
    if "duration_s" in update and update["duration_s"] <= 0:
        raise Reject("SPEC-LAY-05: duration must be positive")
    layers[i] = layers[i].model_copy(update=update)
    return timeline.model_copy(update={"layers": layers})


def remove_layer(timeline: Timeline, layer_id: str) -> Timeline:
    i = _layer_index(timeline, layer_id)
    layer = timeline.layers[i]
    captions = [c for c in timeline.captions if c.id != layer.caption_id] if layer.caption_id else timeline.captions
    layers = [item for item in timeline.layers if item.id != layer_id]
    return timeline.model_copy(update={"layers": layers, "captions": captions})


def reorder_layer(timeline: Timeline, layer_id: str, z: int) -> Timeline:
    i = _layer_index(timeline, layer_id)
    layers = list(timeline.layers)
    layers[i] = layers[i].model_copy(update={"z": int(z)})
    return timeline.model_copy(update={"layers": layers})


def set_transform(timeline: Timeline, layer_id: str, transform: Transform) -> Timeline:
    if not (0.0 <= transform.x <= 1.0 and 0.0 <= transform.y <= 1.0):
        raise Reject("SPEC-LAY-02: x/y must be in [0, 1]")
    if transform.scale <= 0:
        raise Reject("SPEC-LAY-02: scale must be > 0")
    if transform.opacity < 0 or transform.opacity > 1:
        raise Reject("SPEC-LAY-02: opacity must be 0-1")
    i = _layer_index(timeline, layer_id)
    layers = list(timeline.layers)
    layers[i] = layers[i].model_copy(update={"transform": transform})
    return timeline.model_copy(update={"layers": layers})


def add_keyframe(timeline: Timeline, layer_id: str, keyframe: Keyframe) -> Timeline:
    i = _layer_index(timeline, layer_id)
    layer = timeline.layers[i]
    frames = [k for k in layer.keyframes if abs(k.t_s - keyframe.t_s) > 1e-6]
    frames.append(keyframe)
    frames.sort(key=lambda k: k.t_s)
    layers = list(timeline.layers)
    layers[i] = layer.model_copy(update={"keyframes": frames})
    return timeline.model_copy(update={"layers": layers})


def add_effect(timeline: Timeline, target_id: str, effect: EffectInstance) -> Timeline:
    if effect.name not in LEGAL_EFFECTS:
        raise Reject(f"SPEC-RND-16: unknown effect {effect.name}")
    for i, clip in enumerate(timeline.clips):
        if clip.id == target_id:
            clips = list(timeline.clips)
            clips[i] = clip.model_copy(update={"effects": [*clip.effects, effect]})
            return timeline.model_copy(update={"clips": clips})
    i = _layer_index(timeline, target_id)
    layers = list(timeline.layers)
    layer = layers[i]
    layers[i] = layer.model_copy(update={"effects": [*layer.effects, effect]})
    return timeline.model_copy(update={"layers": layers})


def update_effect(timeline: Timeline, effect_id: str, params: dict | None = None, enabled: bool | None = None) -> Timeline:
    def patch(items):
        out = []
        found = False
        for item in items:
            ids = [e.id for e in item.effects]
            if effect_id not in ids:
                out.append(item)
                continue
            found = True
            effects = []
            for effect in item.effects:
                if effect.id != effect_id:
                    effects.append(effect)
                    continue
                update = {}
                if params is not None:
                    update["params"] = {**effect.params, **params}
                if enabled is not None:
                    update["enabled"] = enabled
                effects.append(effect.model_copy(update=update))
            out.append(item.model_copy(update={"effects": effects}))
        return out, found

    clips, found = patch(timeline.clips)
    if found:
        return timeline.model_copy(update={"clips": clips})
    layers, found = patch(timeline.layers)
    if not found:
        raise Reject(f"unknown effect {effect_id}")
    return timeline.model_copy(update={"layers": layers})


def remove_effect(timeline: Timeline, effect_id: str) -> Timeline:
    clips = [c.model_copy(update={"effects": [e for e in c.effects if e.id != effect_id]}) for c in timeline.clips]
    layers = [layer.model_copy(update={"effects": [e for e in layer.effects if e.id != effect_id]}) for layer in timeline.layers]
    return timeline.model_copy(update={"clips": clips, "layers": layers})


def layer_off_canvas(layer: LayerItem) -> bool:
    t = layer.transform
    px = t.x * CANVAS_W
    py = t.y * CANVAS_H
    half_w = CANVAS_W * t.scale / 2
    half_h = CANVAS_H * t.scale / 2
    return px + half_w < 0 or px - half_w > CANVAS_W or py + half_h < 0 or py - half_h > CANVAS_H
