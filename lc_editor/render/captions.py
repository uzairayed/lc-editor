from __future__ import annotations

from pathlib import Path

from lc_editor.fonts import body_font, title_font
from lc_editor.lint.captions import _font_at, fontsize_for, wrap_text
from lc_editor.models import (
    CANVAS_H,
    CANVAS_W,
    CAPTION_BOXW,
    CAPTION_SAFE_X0,
    CAPTION_SAFE_X1,
    KARAOKE_FILL,
    SAND,
    STROKE,
    Caption,
    CaptionWord,
)
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
    if caption.style in ("karaoke", "pop"):
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


CONTRACTIONS = {
    "i'm": ("I", "am"),
    "i've": ("I", "have"),
    "i'll": ("I", "will"),
    "i'd": ("I", "would"),
    "you're": ("you", "are"),
    "we're": ("we", "are"),
    "they're": ("they", "are"),
    "he's": ("he", "is"),
    "she's": ("she", "is"),
    "it's": ("it", "is"),
    "that's": ("that", "is"),
    "what's": ("what", "is"),
    "who's": ("who", "is"),
    "let's": ("let", "us"),
    "don't": ("do", "not"),
    "doesn't": ("does", "not"),
    "didn't": ("did", "not"),
    "can't": ("can", "not"),
    "won't": ("will", "not"),
    "isn't": ("is", "not"),
    "aren't": ("are", "not"),
    "wasn't": ("was", "not"),
    "weren't": ("were", "not"),
    "hasn't": ("has", "not"),
    "haven't": ("have", "not"),
    "hadn't": ("had", "not"),
    "couldn't": ("could", "not"),
    "wouldn't": ("would", "not"),
    "shouldn't": ("should", "not"),
}


def _plain_apos(text: str) -> str:
    return text.replace("’", "'").replace("‘", "'").replace("`", "'")


def expand_contractions(words: list[CaptionWord]) -> list[CaptionWord]:
    out: list[CaptionWord] = []
    for word in words:
        key = _plain_apos(word.text).lower()
        pair = CONTRACTIONS.get(key)
        if pair is None:
            out.append(word)
            continue
        span = max(0.04, word.end_s - word.start_s)
        mid = word.start_s + span / 2
        first, second = pair
        if word.text.isupper():
            first, second = first.upper(), second.upper()
        elif word.text[:1].isupper():
            first = first[:1].upper() + first[1:]
        out.append(word.model_copy(update={"text": first, "end_s": mid, "id": ""}))
        out.append(word.model_copy(update={"text": second, "start_s": mid, "id": ""}))
    return out


def scream_stretch(text: str) -> str:
    letters = [c for c in text if c.isalpha()]
    if len(letters) > 6 or not text:
        return text
    runs = 1
    longest = 1
    for i in range(1, len(text)):
        if text[i].lower() == text[i - 1].lower() and text[i].isalpha():
            runs += 1
            longest = max(longest, runs)
        else:
            runs = 1
    if longest >= 3:
        return text
    last_i = max((i for i, c in enumerate(text) if c.isalpha()), default=len(text) - 1)
    last_c = text[last_i]
    if last_c.lower() in "aeiou":
        return text[:last_i] + last_c * 4 + text[last_i + 1 :]
    return text[: last_i + 1] + last_c * 3 + text[last_i + 1 :]


def ass_time(seconds: float) -> str:
    t = max(0.0, seconds)
    h = int(t // 3600)
    m = int((t % 3600) // 60)
    s = t % 60
    return f"{h}:{m:02d}:{s:05.2f}"


def pop_display_text(word: CaptionWord) -> str:
    text = word.text.replace("'", "").replace("’", "")
    if word.emphasis == "scream":
        return scream_stretch(text)
    return text


def pop_scale_tags(word: CaptionWord) -> str:
    if word.emphasis == "enlarge":
        return r"{\fscx128\fscy128\t(0,90,\fscx145\fscy145)}"
    return r"{\fscx128\fscy128\t(0,90,\fscx100\fscy100)}"


def pop_margin_v(caption: Caption) -> int:
    return max(422, min(900, int(round(CANVAS_H * caption.y_pct - 70))))


def ass_font_name(fontfile: Path | None) -> str:
    if fontfile is None:
        return "Anton"
    stem = fontfile.stem.lower()
    if "clash" in stem:
        return "Clash Display"
    if "anton" in stem:
        return "Anton"
    return fontfile.stem.split("-")[0].replace("Display", " Display")


def pop_ass_body(caption: Caption, clip_start_s: float = 0.0, fontfile: Path | None = None) -> str:
    font = ass_font_name(fontfile or fontfile_for(caption))
    margin_v = pop_margin_v(caption)
    lines = [
        "[Script Info]",
        "ScriptType: v4.00+",
        f"PlayResX: {CANVAS_W}",
        f"PlayResY: {CANVAS_H}",
        "WrapStyle: 2",
        "ScaledBorderAndShadow: yes",
        "",
        "[V4+ Styles]",
        "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding",
        f"Style: Pop,{font},72,&H004AE1FF,&H004AE1FF,&H0010141A,&H00000000,0,0,0,0,100,100,0,0,1,3,2,8,40,40,{margin_v},1",
        "",
        "[Events]",
        "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text",
    ]
    for word in caption.words:
        start = ass_time(clip_start_s + word.start_s)
        end = ass_time(clip_start_s + max(word.end_s, word.start_s + 0.04))
        text = pop_display_text(word)
        if not text:
            continue
        lines.append(f"Dialogue: 0,{start},{end},Pop,,0,0,0,,{pop_scale_tags(word)}{text}")
    return "\n".join(lines) + "\n"


def write_pop_ass(path: Path, caption: Caption, clip_start_s: float = 0.0) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(pop_ass_body(caption, clip_start_s, fontfile_for(caption)), encoding="utf-8")
    return path


def combined_pop_ass(captions: list[Caption], clip_start: dict[str, float], fontfile: Path | None = None) -> str:
    bodies: list[Caption] = [c for c in captions if c.style == "pop" and c.words]
    if not bodies:
        return ""
    first = bodies[0]
    dialogue: list[str] = []
    header = pop_ass_body(first.model_copy(update={"words": []}), 0.0, fontfile)
    header = header.rsplit("[Events]", 1)[0] + "[Events]\nFormat: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n"
    for cap in bodies:
        body = pop_ass_body(cap, clip_start.get(cap.clip_id, 0.0), fontfile)
        for line in body.splitlines():
            if line.startswith("Dialogue:"):
                dialogue.append(line)
    return header + "\n".join(dialogue) + ("\n" if dialogue else "")
