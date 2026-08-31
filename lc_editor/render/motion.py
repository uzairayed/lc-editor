from __future__ import annotations

from lc_editor.models import (
    CANVAS_H,
    CANVAS_W,
    FPS,
    KENBURNS_ZOOM,
    PUNCH_FRAMES,
    PUNCH_ZOOM,
    ZOOM_HIT_AMOUNT,
    ZOOM_HIT_FRAMES,
    Clip,
)


def crop_cover(src_w: int, src_h: int, dest_w: int, dest_h: int, focus_x: float, focus_y: float) -> str:
    target_ratio = dest_w / dest_h if dest_h else 1.0
    src_ratio = src_w / src_h if src_h else target_ratio
    if src_ratio > target_ratio:
        crop_h = src_h
        crop_w = int(src_h * target_ratio)
    else:
        crop_w = src_w
        crop_h = int(src_w / target_ratio)
    crop_w = max(2, crop_w - crop_w % 2)
    crop_h = max(2, crop_h - crop_h % 2)
    dest_w = max(2, dest_w - dest_w % 2)
    dest_h = max(2, dest_h - dest_h % 2)
    x = int(max(0, min(src_w - crop_w, focus_x * src_w - crop_w / 2)))
    y = int(max(0, min(src_h - crop_h, focus_y * src_h - crop_h / 2)))
    return f"crop={crop_w}:{crop_h}:{x}:{y},scale={dest_w}:{dest_h}"


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


def kenburns_filter(frames: int, amount: float = KENBURNS_ZOOM) -> str:
    n = max(frames, 1)
    delta = amount - 1.0
    # smoothstep t*t*(3-2*t) on on/n
    z = f"1+{delta}*(3*pow(on/{n},2)-2*pow(on/{n},3))"
    # zoompan rounds pan offsets to whole pixels per frame; at native res the
    # rounding wobbles the image ("swimming"). Upscaling 4x first makes each
    # rounding step a quarter-pixel after the downscale to canvas size.
    return (
        f"scale={CANVAS_W * 4}:{CANVAS_H * 4},"
        f"zoompan=z='{z}':"
        f"x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':"
        f"d={n}:s={CANVAS_W}x{CANVAS_H}:fps={FPS}"
    )


def punch_filter() -> str:
    return (
        f"scale=w='iw*(1+{PUNCH_ZOOM - 1}*min(1,n/{PUNCH_FRAMES}))':"
        f"h='ih*(1+{PUNCH_ZOOM - 1}*min(1,n/{PUNCH_FRAMES}))':eval=frame,"
        f"crop={CANVAS_W}:{CANVAS_H}"
    )


def zoom_hit_filter(
    motion: str,
    frames: int = ZOOM_HIT_FRAMES,
    amount: float = ZOOM_HIT_AMOUNT,
) -> str:
    n = max(1, int(frames))
    delta = round(amount - 1.0, 4)
    if motion == "zoom_out":
        z = f"1+{delta}*(1-min(1,n/{n}))"
    else:
        z = f"1+{delta}*min(1,n/{n})"
    return (
        f"scale=w='iw*({z})':h='ih*({z})':eval=frame,"
        f"crop={CANVAS_W}:{CANVAS_H}"
    )


def motion_chain(clip: Clip, frames: int) -> str:
    if clip.motion == "kenburns":
        return kenburns_filter(frames, clip.kenburns_amount)
    if clip.motion == "punch":
        return punch_filter()
    if clip.motion in ("zoom_in", "zoom_out"):
        return zoom_hit_filter(clip.motion, clip.zoom_frames, clip.zoom_amount)
    return f"scale={CANVAS_W}:{CANVAS_H}"
