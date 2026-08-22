from __future__ import annotations

from pathlib import Path

from lc_editor.fonts import body_font, title_font
from lc_editor.models import SAND, STROKE, STROKE_W, Caption
from lc_editor.render.paths import ffmpeg_path


def write_textfile(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8", newline="\n")
    raw = path.read_bytes()
    if raw.endswith(b"\n"):
        path.write_bytes(raw.rstrip(b"\r\n"))
    return path


def fontsize_for(caption: Caption) -> int:
    if caption.role == "title" and len(caption.text) < 12:
        return 84
    if caption.role == "title":
        return 72
    return 68


def fontfile_for(caption: Caption) -> Path | None:
    return title_font() if caption.role == "title" else body_font()


def drawtext_filter(caption: Caption, textfile: Path, fontfile: Path | None) -> str:
    tf = ffmpeg_path(textfile)
    font = f":fontfile='{ffmpeg_path(fontfile)}'" if fontfile else ""
    size = fontsize_for(caption)
    y = f"h*{caption.y_pct:.2f}-text_h/2"
    return (
        f"drawtext=textfile='{tf}':expansion=none{font}:"
        f"fontsize={size}:fontcolor={SAND}:"
        f"bordercolor={STROKE}:borderw={STROKE_W}:"
        f"shadowcolor=black@0.5:shadowx=2:shadowy=2:"
        f"x=(w-text_w)/2:y={y}"
    )
