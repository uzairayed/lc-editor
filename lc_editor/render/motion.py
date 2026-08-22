from __future__ import annotations

from lc_editor.models import (
    CANVAS_H,
    CANVAS_W,
    FPS,
    KENBURNS_ZOOM,
    PUNCH_FRAMES,
    PUNCH_ZOOM,
    Clip,
)


def crop_9_16(clip: Clip, src_w: int, src_h: int) -> str:
    target_ratio = CANVAS_W / CANVAS_H
    src_ratio = src_w / src_h if src_h else target_ratio
    if src_ratio > target_ratio:
        crop_h = src_h
        crop_w = int(src_h * target_ratio)
    else:
        crop_w = src_w
        crop_h = int(src_w / target_ratio)
    x = int(max(0, min(src_w - crop_w, clip.focus_x * src_w - crop_w / 2)))
    y = int(max(0, min(src_h - crop_h, clip.focus_y * src_h - crop_h / 2)))
    return f"crop={crop_w}:{crop_h}:{x}:{y},scale={CANVAS_W}:{CANVAS_H}"


def kenburns_filter(frames: int) -> str:
    n = max(frames, 1)
    return (
        f"zoompan=z='min({KENBURNS_ZOOM},1+0.06*on/{n})':"
        f"x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':"
        f"d={n}:s={CANVAS_W}x{CANVAS_H}:fps={FPS}"
    )


def punch_filter() -> str:
    return (
        f"scale=w='iw*(1+{PUNCH_ZOOM - 1}*min(1,n/{PUNCH_FRAMES}))':"
        f"h='ih*(1+{PUNCH_ZOOM - 1}*min(1,n/{PUNCH_FRAMES}))':eval=frame,"
        f"crop={CANVAS_W}:{CANVAS_H}"
    )


def motion_chain(clip: Clip, frames: int) -> str:
    if clip.motion == "kenburns":
        return kenburns_filter(frames)
    if clip.motion == "punch":
        return punch_filter()
    return f"scale={CANVAS_W}:{CANVAS_H}"
