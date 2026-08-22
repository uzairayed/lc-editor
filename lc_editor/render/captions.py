from __future__ import annotations

from pathlib import Path

from lc_editor.fonts import body_font, title_font
from lc_editor.models import SAND, STROKE, Caption
from lc_editor.render.paths import ffmpeg_path


def write_textfile(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8", newline="\n")
    raw = path.read_bytes()
    if raw.endswith(b"\n"):
        path.write_bytes(raw.rstrip(b"\r\n"))
    return path


def fontsize_for(caption: Caption) -> int:
    if caption.role == "title" and len(caption.text) <= 12:
        return 84
    if caption.role == "title":
        return 70
    return 64


def stroke_w(caption: Caption) -> int:
    return 4 if caption.role == "title" else 3


def fontfile_for(caption: Caption) -> Path | None:
    return title_font() if caption.role == "title" else body_font()


def enter_exprs(caption: Caption, size: int) -> tuple[str, str]:
    kind = caption.enter
    if kind == "punch":
        return f"{size}*(1+0.02*min(1\\,n/3))", ""
    if kind == "fade":
        return str(size), ":alpha='if(lt(n,4),n/4,1)'"
    return str(size), ""


def drawtext_filter(caption: Caption, textfile: Path, fontfile: Path | None) -> str:
    tf = ffmpeg_path(textfile)
    font = f":fontfile='{ffmpeg_path(fontfile)}'" if fontfile else ""
    size = fontsize_for(caption)
    size_expr, alpha = enter_exprs(caption, size)
    y = f"h*{caption.y_pct:.2f}-text_h/2"
    return (
        f"drawtext=textfile='{tf}':expansion=none{font}:"
        f"fontsize={size_expr}:fontcolor={SAND}:"
        f"bordercolor={STROKE}:borderw={stroke_w(caption)}:"
        f"shadowcolor=black@0.5:shadowx=2:shadowy=2:"
        f"x=(w-text_w)/2:y={y}{alpha}"
    )
