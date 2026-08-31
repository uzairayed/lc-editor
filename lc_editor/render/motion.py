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
    ZOOM_PAIR_MIN_HOLD_S,
    Clip,
)


def even_px(n: int) -> int:
    return max(2, int(n) - int(n) % 2)


def even_expr(expr: str) -> str:
    return f"trunc(({expr})/2)*2"


def cover_scale_crop(dest_w: int, dest_h: int, focus_x: float = 0.5, focus_y: float = 0.5) -> str:
    dest_w = even_px(dest_w)
    dest_h = even_px(dest_h)
    x = even_expr(f"max(0,min(iw-{dest_w},iw*{focus_x}-{dest_w}/2))")
    y = even_expr(f"max(0,min(ih-{dest_h},ih*{focus_y}-{dest_h}/2))")
    return (
        f"scale={dest_w}:{dest_h}:force_original_aspect_ratio=increase,"
        f"crop={dest_w}:{dest_h}:'{x}':'{y}'"
    )


def crop_cover(src_w: int, src_h: int, dest_w: int, dest_h: int, focus_x: float, focus_y: float) -> str:
    del src_w, src_h
    return cover_scale_crop(dest_w, dest_h, focus_x, focus_y)


def crop_9_16(clip: Clip, src_w: int, src_h: int) -> str:
    return crop_cover(src_w, src_h, CANVAS_W, CANVAS_H, clip.focus_x, clip.focus_y)


def kenburns_filter(frames: int, amount: float = KENBURNS_ZOOM) -> str:
    n = max(frames, 1)
    delta = amount - 1.0
    # smoothstep t*t*(3-2*t) on on/n
    z = f"1+{delta}*(3*pow(on/{n},2)-2*pow(on/{n},3))"
    # zoompan rounds pan offsets to whole pixels per frame; at native res the
    # rounding wobbles the image ("swimming"). Upscaling 4x first makes each
    # rounding step a quarter-pixel after the downscale to canvas size.
    # yuv444p keeps chroma 1:1 while zoompan's iw/zoom window is often odd,
    # which otherwise leaves a 1px red/blue line on the right in yuv420p.
    w4 = CANVAS_W * 4
    h4 = CANVAS_H * 4
    return (
        f"format=yuv444p,"
        f"{cover_scale_crop(w4, h4)},"
        f"zoompan=z='{z}':"
        f"x='{even_expr('iw/2-(iw/zoom/2)')}':"
        f"y='{even_expr('ih/2-(ih/zoom/2)')}':"
        f"d={n}:s={CANVAS_W}x{CANVAS_H}:fps={FPS}"
    )


def _scale_crop_zoom(z: str) -> str:
    return (
        f"scale=w='{even_expr(f'iw*({z})')}':"
        f"h='{even_expr(f'ih*({z})')}':eval=frame,"
        f"crop={CANVAS_W}:{CANVAS_H}:"
        f"'{even_expr(f'(iw-{CANVAS_W})/2')}':"
        f"'{even_expr(f'(ih-{CANVAS_H})/2')}'"
    )


def punch_filter() -> str:
    return _scale_crop_zoom(f"1+{PUNCH_ZOOM - 1}*min(1,n/{PUNCH_FRAMES})")


def ease_in_out_cubic_expr(t: str) -> str:
    return f"if(lt({t}\\,0.5)\\,4*pow({t}\\,3)\\,1-pow(-2*{t}+2\\,3)/2)"


def zoom_hit_filter(
    motion: str,
    frames: int = ZOOM_HIT_FRAMES,
    amount: float = ZOOM_HIT_AMOUNT,
) -> str:
    n = max(1, int(frames))
    delta = round(amount - 1.0, 4)
    t = f"min(1\\,n/{n})"
    u = ease_in_out_cubic_expr(t)
    if motion == "zoom_out":
        z = f"1+{delta}*(1-({u}))"
    else:
        z = f"1+{delta}*({u})"
    return _scale_crop_zoom(z)


def zoom_pair_filter(
    duration_s: float,
    amount: float = ZOOM_HIT_AMOUNT,
    frames_in: int = ZOOM_HIT_FRAMES,
    frames_out: int = ZOOM_HIT_FRAMES,
    at_s: float | None = None,
) -> str:
    total = max(1, int(round(float(duration_s) * FPS)))
    nin = max(1, int(frames_in))
    nout = max(1, int(frames_out))
    start = 0.15 * duration_s if at_s is None else float(at_s)
    n0 = max(0, int(round(start * FPS)))
    n1 = max(n0 + nin, total - nout)
    hold = int(round(ZOOM_PAIR_MIN_HOLD_S * FPS))
    if n1 < n0 + nin + hold:
        n0 = 0
        n1 = max(nin + hold, total - nout)
    n1 = min(n1, total - nout)
    delta = round(amount - 1.0, 4)
    t_in = f"min(1\\,max(0\\,(n-{n0})/{nin}))"
    t_out = f"min(1\\,max(0\\,(n-{n1})/{nout}))"
    u_in = ease_in_out_cubic_expr(t_in)
    u_out = ease_in_out_cubic_expr(t_out)
    z = (
        f"if(lt(n\\,{n0})\\,1\\,"
        f"if(lt(n\\,{n0 + nin})\\,1+{delta}*({u_in})\\,"
        f"if(lt(n\\,{n1})\\,1+{delta}\\,"
        f"if(lt(n\\,{n1 + nout})\\,1+{delta}*(1-({u_out}))\\,1))))"
    )
    return _scale_crop_zoom(z)


def motion_chain(clip: Clip, frames: int) -> str:
    if clip.motion == "kenburns":
        return kenburns_filter(frames, clip.kenburns_amount)
    if clip.motion == "punch":
        return punch_filter()
    if clip.motion in ("zoom_in", "zoom_out"):
        return zoom_hit_filter(clip.motion, clip.zoom_frames, clip.zoom_amount)
    if clip.motion == "zoom_pair":
        return zoom_pair_filter(
            clip.duration_s,
            clip.zoom_amount,
            clip.zoom_frames,
            clip.zoom_frames_out,
            clip.zoom_at_s,
        )
    return f"scale={CANVAS_W}:{CANVAS_H}"
