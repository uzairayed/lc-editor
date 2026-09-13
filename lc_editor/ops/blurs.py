from __future__ import annotations

from lc_editor.models import (
    BLUR_FEATHER_DEFAULT,
    BLUR_FEATHER_MAX,
    BLUR_FEATHER_MIN,
    BLUR_STRENGTH_DEFAULT,
    BLUR_STRENGTH_MAX,
    BLUR_STRENGTH_MIN,
    LEGAL_BLUR_KINDS,
    ClipBlur,
    Timeline,
)
from lc_editor.ops.timeline import Reject, _clip_index


def validate_blur_box(x: float, y: float, w: float, h: float) -> tuple[float, float, float, float]:
    try:
        nx, ny, nw, nh = float(x), float(y), float(w), float(h)
    except (TypeError, ValueError) as exc:
        raise Reject("SPEC-FX-11: blur box x,y,w,h must be numbers") from exc
    if nw <= 0 or nh <= 0:
        raise Reject("SPEC-FX-11: blur box w,h must be > 0")
    if not (0.0 <= nx <= 1.0 and 0.0 <= ny <= 1.0):
        raise Reject("SPEC-FX-11: blur box x,y must be in [0, 1] (top-left of post-fit frame)")
    if nx + nw > 1.001 or ny + nh > 1.001:
        raise Reject("SPEC-FX-11: blur box must stay inside the frame (x+w,y+h <= 1)")
    return (
        round(max(0.0, min(1.0, nx)), 4),
        round(max(0.0, min(1.0, ny)), 4),
        round(max(0.01, min(1.0 - nx, nw)), 4),
        round(max(0.01, min(1.0 - ny, nh)), 4),
    )


def validate_blur_strength(strength: float | None) -> float:
    value = BLUR_STRENGTH_DEFAULT if strength is None else float(strength)
    if value < BLUR_STRENGTH_MIN or value > BLUR_STRENGTH_MAX:
        raise Reject(f"SPEC-FX-11: strength must be {BLUR_STRENGTH_MIN}-{BLUR_STRENGTH_MAX} px at 1080")
    return round(value, 2)


def validate_blur_feather(feather: float | None) -> float:
    value = BLUR_FEATHER_DEFAULT if feather is None else float(feather)
    if value < BLUR_FEATHER_MIN or value > BLUR_FEATHER_MAX:
        raise Reject(f"SPEC-FX-11: feather must be {BLUR_FEATHER_MIN}-{BLUR_FEATHER_MAX} px at 1080")
    return round(value, 2)


def validate_blur_kind(kind: str) -> str:
    if kind not in LEGAL_BLUR_KINDS:
        raise Reject(f"SPEC-FX-11: kind must be one of {', '.join(LEGAL_BLUR_KINDS)}")
    return kind


def add_blur(timeline: Timeline, clip_id: str, blur: ClipBlur) -> Timeline:
    i = _clip_index(timeline, clip_id)
    clip = timeline.clips[i]
    clips = list(timeline.clips)
    clips[i] = clip.model_copy(update={"blurs": [*clip.blurs, blur]})
    return timeline.model_copy(update={"clips": clips})


def update_blur(
    timeline: Timeline,
    blur_id: str,
    *,
    x: float | None = None,
    y: float | None = None,
    w: float | None = None,
    h: float | None = None,
    strength: float | None = None,
    feather: float | None = None,
) -> Timeline:
    for ci, clip in enumerate(timeline.clips):
        for bi, blur in enumerate(clip.blurs):
            if blur.id != blur_id:
                continue
            nx = blur.x if x is None else x
            ny = blur.y if y is None else y
            nw = blur.w if w is None else w
            nh = blur.h if h is None else h
            box = validate_blur_box(nx, ny, nw, nh)
            update: dict = {"x": box[0], "y": box[1], "w": box[2], "h": box[3]}
            if strength is not None:
                update["strength"] = validate_blur_strength(strength)
            if feather is not None:
                update["feather"] = validate_blur_feather(feather)
            blurs = list(clip.blurs)
            blurs[bi] = blur.model_copy(update=update)
            clips = list(timeline.clips)
            clips[ci] = clip.model_copy(update={"blurs": blurs})
            return timeline.model_copy(update={"clips": clips})
    raise Reject(f"unknown blur {blur_id}")


def remove_blur(timeline: Timeline, blur_id: str) -> Timeline:
    found = False
    clips = []
    for clip in timeline.clips:
        keep = [b for b in clip.blurs if b.id != blur_id]
        if len(keep) != len(clip.blurs):
            found = True
        clips.append(clip.model_copy(update={"blurs": keep}))
    if not found:
        raise Reject(f"unknown blur {blur_id}")
    return timeline.model_copy(update={"clips": clips})


def list_blurs(timeline: Timeline, clip_id: str | None = None) -> list[dict]:
    out: list[dict] = []
    for clip in timeline.clips:
        if clip_id is not None and clip.id != clip_id:
            continue
        for blur in clip.blurs:
            row = blur.model_dump()
            row["clip_id"] = clip.id
            out.append(row)
    if clip_id is not None:
        _clip_index(timeline, clip_id)
    return out
