from __future__ import annotations

from pathlib import Path

from lc_editor.fonts import body_font, title_font
from lc_editor.lint.captions import _font_at, fontsize_for, wrap_text
from lc_editor.models import CANVAS_W, CAPTION_BOXW, CAPTION_SAFE_X0, CAPTION_SAFE_X1, KARAOKE_FILL, SAND, STROKE, Caption
from lc_editor.render.paths import ffmpeg_path


def write_textfile(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8", newline="\n")
    raw = path.read_bytes()
    if raw.endswith(b"\n"):
        path.write_bytes(raw.rstrip(b"\r\n"))
    return path


def caption_textfile_body(caption: Caption) -> str:
    lines = caption.lines or wrap_text(caption.text)
    return "\n".join(lines)


def stroke_w(caption: Caption) -> int:
    return 4 if caption.role == "title" else 3


def fontfile_for(caption: Caption) -> Path | None:
    if caption.style == "karaoke":
        return title_font()
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
    # Prefer canvas center; bias left so the glyph block stays in x 64-853.
    x = (
        f"max({CAPTION_SAFE_X0}\\,min((w-text_w)/2\\,{CAPTION_SAFE_X1}-text_w))"
    )
    return (
        f"drawtext=textfile='{tf}':expansion=none{font}:"
        f"fontsize={size_expr}:fontcolor={SAND}:"
        f"bordercolor={STROKE}:borderw={stroke_w(caption)}:"
        f"shadowcolor=black@0.5:shadowx=2:shadowy=2:"
        f"boxw={CAPTION_BOXW}:"
        f"x={x}:y={y}{alpha}"
    )


def word_textfiles(caption: Caption) -> list[Path]:
    parent = Path(caption.textfile).parent if caption.textfile else Path(".")
    return [parent / f"{caption.id}_w{i}.txt" for i in range(len(caption.words))]


def karaoke_filters(caption: Caption, word_files: list[Path], fontfile: Path | None) -> list[str]:
    size = fontsize_for(caption)
    font = _font_at("title", size)
    space = max(8, font.getbbox(" ")[2] - font.getbbox(" ")[0])
    widths: list[int] = []
    for word in caption.words:
        box = font.getbbox(word.text or " ")
        widths.append(box[2] - box[0])
    total = sum(widths) + space * max(0, len(widths) - 1)
    x0 = int(round((CANVAS_W - total) / 2))
    x0 = max(CAPTION_SAFE_X0, min(x0, CAPTION_SAFE_X1 - total))
    y = f"h*{caption.y_pct:.2f}-text_h/2"
    font_bit = f":fontfile='{ffmpeg_path(fontfile)}'" if fontfile else ""
    filters: list[str] = []
    cursor = x0
    for word, path, width in zip(caption.words, word_files, widths, strict=False):
        color = (
            f"if(between(t\\,{word.start_s:.4f}\\,{word.end_s:.4f})\\,{KARAOKE_FILL}\\,{SAND})"
        )
        tf = ffmpeg_path(path)
        filters.append(
            f"drawtext=textfile='{tf}':expansion=none{font_bit}:"
            f"fontsize={size}:fontcolor='{color}':"
            f"bordercolor={STROKE}:borderw={stroke_w(caption)}:"
            f"shadowcolor=black@0.5:shadowx=2:shadowy=2:"
            f"x={cursor}:y={y}"
        )
        cursor += width + space
    return filters
