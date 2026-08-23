from __future__ import annotations

from pathlib import Path

from lc_editor.models import CANVAS_H, CANVAS_W, FPS, LayerItem, SAND, STROKE
from lc_editor.render.captions import fontsize_for
from lc_editor.render.paths import ffmpeg_path
from lc_editor.fonts import body_font, title_font
from lc_editor.models import Caption


def _fontfile(layer: LayerItem) -> Path | None:
    return title_font() if layer.role == "title" or layer.style.role == "title" else body_font()


def _size(layer: LayerItem) -> int:
    dummy = Caption(id=layer.id, clip_id=layer.clip_id or "", text=layer.text, role=layer.role)
    return fontsize_for(dummy)


def text_motion_exprs(layer: LayerItem, size: int) -> tuple[str, str, str]:
    motion = layer.style.motion
    if motion == "pop":
        return f"{size}*(1+0.02*min(1\\,n/3))", "", ""
    if motion == "fade":
        return str(size), ":alpha='if(lt(n,4),n/4,1)'", ""
    if motion == "slide":
        y = f"h*{layer.y_pct:.2f}-text_h/2 + 48*(1-min(1\\,n/4))"
        return str(size), ":alpha='if(lt(n,4),n/4,1)'", y
    if motion == "type_on":
        chars = max(1, len(layer.text))
        frames = max(4, int(round(0.4 * FPS)))
        return str(size), f":enable='gte(n,0)':text_shaping=0", f"h*{layer.y_pct:.2f}-text_h/2"
    return str(size), "", ""


def layer_drawtext(layer: LayerItem, textfile: Path) -> str:
    tf = ffmpeg_path(textfile)
    fontfile = _fontfile(layer)
    font = f":fontfile='{ffmpeg_path(fontfile)}'" if fontfile else ""
    size = _size(layer)
    size_expr, extra, y_override = text_motion_exprs(layer, size)
    y = y_override or f"h*{layer.y_pct:.2f}-text_h/2"
    x = f"(w-text_w)/2+{(layer.transform.x - 0.5) * CANVAS_W:.1f}"
    fill = layer.style.fill or SAND
    stroke = layer.style.stroke or STROKE
    borderw = layer.style.stroke_w or 3
    enable = f":enable='between(t,{layer.start_s:.4f},{layer.start_s + layer.duration_s:.4f})'"
    alpha = ""
    if layer.transform.opacity < 0.999:
        alpha = f":alpha='{layer.transform.opacity:.3f}'"
    return (
        f"drawtext=textfile='{tf}':expansion=none{font}:"
        f"fontsize={size_expr}:fontcolor={fill}:"
        f"bordercolor={stroke}:borderw={borderw}:"
        f"shadowcolor=black@0.5:shadowx=2:shadowy=2:"
        f"x={x}:y={y}{extra}{alpha}{enable}"
    )


def interpolate_keyframes(layer: LayerItem, field: str, t: str = "t") -> str:
    frames = sorted(layer.keyframes, key=lambda k: k.t_s)
    base = getattr(layer.transform, field)
    if not frames:
        return f"{base}"
    expr = f"{base}"
    prev_t = 0.0
    prev_v = base
    for kf in frames:
        value = getattr(kf, field)
        if value is None:
            continue
        start = layer.start_s + kf.t_s
        if kf.ease == "linear":
            mix = f"({t}-{prev_t:.4f})/{max(kf.t_s - (prev_t - layer.start_s), 0.001):.4f}"
        else:
            raw = f"({t}-{start:.4f})/0.001"
            mix = f"(3*pow(min(1\\,max(0\\,{raw})),2)-2*pow(min(1\\,max(0\\,{raw})),3))"
        expr = f"if(lt({t}\\,{start:.4f}),{expr},{prev_v}+({value}-{prev_v})*{mix})"
        prev_t = start
        prev_v = value
    return expr
