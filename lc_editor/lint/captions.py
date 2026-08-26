from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from lc_editor.fonts import font_for
from lc_editor.models import (
    CANVAS_H,
    CANVAS_W,
    CAPTION_BAND_Y0,
    CAPTION_BAND_Y1,
    CAPTION_BOXW,
    CAPTION_HOLD_CAP_S,
    CAPTION_LINE_MAX,
    CAPTION_MAX_LINES,
    CAPTION_MAX_WORDS,
    CAPTION_PROTECT_PX,
    CAPTION_SAFE_X0,
    CAPTION_SAFE_X1,
    CAPTION_SAFE_Y0,
    CAPTION_SAFE_Y1,
    CAPTION_SIZE_MIN,
    CAPTION_WRAP,
    CAPTION_Y_MAX,
    CAPTION_Y_MIN,
    PHONE_PROOF_H,
    PHONE_PROOF_W,
    Caption,
    Clip,
    MediaItem,
    Project,
    Timeline,
)


def wrap_text(text: str, width: int = CAPTION_WRAP) -> list[str]:
    words = text.split()
    if not words:
        return [""]
    lines: list[str] = []
    current = ""
    for word in words:
        trial = word if not current else f"{current} {word}"
        if len(trial) <= width:
            current = trial
        else:
            if current:
                lines.append(current)
            current = word
    if current:
        lines.append(current)
    return lines


def word_count(text: str) -> int:
    return len(text.split())


def hold_s(text: str, lines: list[str]) -> float:
    chars = len(text.rstrip())
    floor = 1.8 if len(lines) >= 2 else 1.5
    raw = chars / 18 + 0.4
    return round(min(CAPTION_HOLD_CAP_S, max(floor, raw)), 2)


def is_all_caps(text: str) -> bool:
    letters = [c for c in text if c.isalpha()]
    if len(letters) < 6:
        return False
    return all(c.isupper() for c in letters)


def base_fontsize(caption: Caption) -> int:
    if caption.role == "title" and len(caption.text) <= 12:
        return 84
    if caption.role == "title":
        return 70
    return 64


def _stroke_pad(role: str) -> int:
    return (4 if role == "title" else 3) + 2


def _font_at(role: str, size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    path = font_for(role if role in ("title", "body") else "body")
    if path:
        try:
            return ImageFont.truetype(str(path), size)
        except OSError:
            pass
    return ImageFont.load_default()


def _measure(lines: list[str], role: str, size: int) -> tuple[float, float]:
    font = _font_at(role, size)
    widths: list[int] = []
    heights: list[int] = []
    for line in lines:
        box = font.getbbox(line or " ")
        widths.append(box[2] - box[0])
        heights.append(box[3] - box[1])
    width = max(widths) if widths else 0
    line_h = max(heights) if heights else size
    gap = int(size * 0.18)
    height = line_h * len(lines) + gap * max(0, len(lines) - 1)
    pad = _stroke_pad(role)
    return float(width + 2 * pad), float(height + 2 * pad)


def fontsize_for(caption: Caption) -> int:
    lines = caption.lines or wrap_text(caption.text)
    base = base_fontsize(caption)
    for size in range(base, CAPTION_SIZE_MIN - 1, -2):
        width, _ = _measure(lines, caption.role, size)
        if width <= CAPTION_BOXW:
            return size
    return CAPTION_SIZE_MIN


def _font(caption: Caption, size: int | None = None) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    return _font_at(caption.role, size or fontsize_for(caption))


def estimate_bbox(caption: Caption) -> dict:
    lines = caption.lines or wrap_text(caption.text)
    size = fontsize_for(caption)
    width, height = _measure(lines, caption.role, size)
    cy = CANVAS_H * caption.y_pct
    y0 = cy - height / 2
    y2 = cy + height / 2
    preferred_x0 = (CANVAS_W - width) / 2
    if width <= CAPTION_BOXW:
        x0 = min(max(preferred_x0, float(CAPTION_SAFE_X0)), float(CAPTION_SAFE_X1) - width)
    else:
        x0 = preferred_x0
    x2 = x0 + width
    return {
        "x": round(x0, 1),
        "y": round(y0, 1),
        "w": round(width, 1),
        "h": round(height, 1),
        "x2": round(x2, 1),
        "y2": round(y2, 1),
        "cx": round((x0 + x2) / 2, 1),
        "cy": round(cy, 1),
        "size": size,
    }


def luma_rgb(rgb: tuple[int, int, int]) -> float:
    r, g, b = (c / 255.0 for c in rgb[:3])
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def _open_still(path: str | Path | None) -> Image.Image | None:
    if not path:
        return None
    src = Path(path)
    if not src.exists() or src.stat().st_size < 200:
        return None
    try:
        im = Image.open(src).convert("RGB")
    except OSError:
        return None
    if im.size != (CANVAS_W, CANVAS_H):
        im = im.resize((CANVAS_W, CANVAS_H))
    return im


def sample_underlay_luma(path: str | Path | None, bbox: dict) -> float | None:
    im = _open_still(path)
    if im is None:
        return None
    x0 = max(0, int(bbox["x"]))
    y0 = max(0, int(bbox["y"]))
    x1 = min(im.width, int(bbox["x2"]))
    y1 = min(im.height, int(bbox["y2"]))
    if x1 <= x0 or y1 <= y0:
        return None
    crop = im.crop((x0, y0, x1, y1))
    pixels = list(crop.getdata())
    if not pixels:
        return None
    return sum(luma_rgb(p) for p in pixels) / len(pixels)


def contrast_too_close(luma: float | None) -> bool:
    return luma is not None and 0.70 <= luma <= 1.0


def _protect_overlap(bbox: dict, clip: Clip | None) -> bool:
    if clip is None or not clip.protect:
        return False
    fx = clip.focus_x * CANVAS_W
    fy = clip.focus_y * CANVAS_H
    nearest_x = min(max(fx, bbox["x"]), bbox["x2"])
    nearest_y = min(max(fy, bbox["y"]), bbox["y2"])
    dist = ((fx - nearest_x) ** 2 + (fy - nearest_y) ** 2) ** 0.5
    return dist < CAPTION_PROTECT_PX


def caption_issues(
    text: str,
    *,
    y_pct: float,
    clip: Clip | None,
    box: bool = False,
    lines: list[str] | None = None,
    role: str = "body",
    underlay_path: str | None = None,
    caption: Caption | None = None,
) -> list[str]:
    warnings: list[str] = []
    if box:
        warnings.append("SPEC-CRAFT-02: caption background is forbidden")
        warnings.append("SPEC-CAP-04: caption box is forbidden")
    if is_all_caps(text):
        warnings.append("SPEC-CAP-04: ALL CAPS is rejected; use sentence case")
    wrapped = lines if lines is not None else wrap_text(text)
    if len(wrapped) > CAPTION_MAX_LINES:
        warnings.append("SPEC-CAP-02: caption wraps past 3 lines")
    if word_count(text) > CAPTION_MAX_WORDS:
        warnings.append("SPEC-CAP-02: caption exceeds ~16 words")
    if any(len(line) > CAPTION_LINE_MAX for line in wrapped):
        warnings.append("SPEC-CAP-02: wrapped line exceeds 28 characters")
    if any(line.strip() == "" for line in wrapped):
        warnings.append("SPEC-CAP-02: caption has an empty line")
    if y_pct < CAPTION_Y_MIN or y_pct > CAPTION_Y_MAX:
        warnings.append("SPEC-CAP-03: caption Y outside 22-50% safe zone")
    if clip is not None and wrapped and len(wrapped) <= CAPTION_MAX_LINES:
        need = hold_s(text, wrapped)
        if clip.duration_s + 1e-9 < need:
            warnings.append(
                f"SPEC-CAP-02: clip {clip.duration_s:.2f}s shorter than hold {need:.2f}s; "
                "extend the clip or drop the text"
            )
    probe = caption or Caption(
        id="tmp",
        clip_id=clip.id if clip else "c",
        text=text,
        role=role if role in ("title", "body") else "body",
        y_pct=y_pct,
        lines=wrapped,
    )
    bbox = estimate_bbox(probe)
    if bbox["x"] < 0 or bbox["y"] < 0 or bbox["x2"] > CANVAS_W or bbox["y2"] > CANVAS_H:
        warnings.append(
            "SPEC-CAP-03: caption bbox clips the 1080x1920 frame; "
            "caption_move / wrap / smaller size. Never add a box."
        )
    if bbox["y"] < CAPTION_BAND_Y0 or bbox["y2"] > CAPTION_BAND_Y1:
        warnings.append(
            "SPEC-CAP-03: caption block leaves the 22-50% band; "
            "caption_move / wrap / smaller size. Never add a box."
        )
    if bbox["x"] < CAPTION_SAFE_X0 or bbox["y"] < CAPTION_SAFE_Y0 or bbox["y2"] > CAPTION_SAFE_Y1:
        warnings.append("SPEC-CAP-03: caption bbox leaves the cross-post safe rect")
    if bbox["x2"] > CAPTION_SAFE_X1:
        warnings.append(
            "SPEC-CAP-03: caption bbox crosses the right action column (x2 > 853); "
            "wrap / smaller size. Never add a box."
        )
    if _protect_overlap(bbox, clip):
        warnings.append("SPEC-CAP-03: caption overlaps a protected focus point")
    luma = sample_underlay_luma(underlay_path, bbox)
    if contrast_too_close(luma):
        warnings.append(
            "SPEC-CAP-06: underlay is too close to sand; caption_move to a darker band or recut. Never add a box."
        )
    return warnings


def density_warnings(timeline: Timeline, project: Project | None = None) -> list[str]:
    warnings: list[str] = []
    n_clips = len(timeline.clips)
    if n_clips >= 8 and n_clips and len(timeline.captions) / n_clips > 0.7:
        warnings.append("SPEC-CAP-07: caption density is over 0.7 (wall of text)")
    if project is not None and project.preset == "karachi":
        early = {c.id for c in timeline.clips if c.start_s < 1.5}
        has_hook = any(cap.role == "title" and cap.clip_id in early for cap in timeline.captions)
        if not has_hook:
            warnings.append("SPEC-CAP-07: karachi preset has no title hook in the first 1.5s")
    return warnings


def timeline_caption_issues(
    timeline: Timeline,
    *,
    media: list[MediaItem] | None = None,
    project: Project | None = None,
) -> list[str]:
    clips = {c.id: c for c in timeline.clips}
    media_map = {m.id: m for m in (media or [])}
    warnings: list[str] = []
    for cap in timeline.captions:
        clip = clips.get(cap.clip_id)
        item = media_map.get(clip.media_id) if clip else None
        warnings.extend(
            caption_issues(
                cap.text,
                y_pct=cap.y_pct,
                clip=clip,
                lines=cap.lines,
                role=cap.role,
                underlay_path=item.path if item else None,
                caption=cap,
            )
        )
    return warnings


def card_report(
    caption: Caption,
    clip: Clip | None,
    media: MediaItem | None = None,
) -> dict:
    bbox = estimate_bbox(caption)
    luma = sample_underlay_luma(media.path if media else None, bbox)
    return {
        "id": caption.id,
        "hold_s": caption.hold_s,
        "lines": caption.lines or wrap_text(caption.text),
        "bbox": bbox,
        "contrast": {"luma": luma, "ok": not contrast_too_close(luma)},
        "enter": caption.enter,
        "role": caption.role,
    }


def draw_caption_card(im: Image.Image, caption: Caption) -> Image.Image:
    canvas = im.copy()
    draw = ImageDraw.Draw(canvas)
    size = fontsize_for(caption)
    font = _font(caption, size)
    lines = caption.lines or wrap_text(caption.text)
    bbox = estimate_bbox(caption)
    stroke = 4 if caption.role == "title" else 3
    y = bbox["y"] + _stroke_pad(caption.role)
    line_count = max(1, len(lines))
    inner_h = bbox["h"] - 2 * _stroke_pad(caption.role)
    line_h = inner_h / line_count
    for line in lines:
        box = font.getbbox(line)
        w = box[2] - box[0]
        x = bbox["x"] + (bbox["w"] - w) / 2
        draw.text(
            (x, y),
            line,
            font=font,
            fill=(246, 235, 212),
            stroke_width=stroke,
            stroke_fill=(26, 20, 16),
        )
        y += line_h
    return canvas


def phone_proof_issues(proof: Image.Image, caption: Caption) -> list[str]:
    issues: list[str] = []
    if proof.size != (PHONE_PROOF_W, PHONE_PROOF_H):
        issues.append("SPEC-CAP-08: phone proof is not 270x480")
        return issues
    bbox = estimate_bbox(caption)
    sx = PHONE_PROOF_W / CANVAS_W
    sy = PHONE_PROOF_H / CANVAS_H
    x0 = bbox["x"] * sx
    y0 = bbox["y"] * sy
    x1 = bbox["x2"] * sx
    y1 = bbox["y2"] * sy
    if x0 < -2 or y0 < -2 or x1 > PHONE_PROOF_W + 2 or y1 > PHONE_PROOF_H + 2:
        issues.append("SPEC-CAP-08: caption clips the phone-proof frame")
    crop = proof.crop(
        (
            max(0, int(x0) - 2),
            max(0, int(y0) - 2),
            min(proof.width, int(x1) + 2),
            min(proof.height, int(y1) + 2),
        )
    )
    if crop.width == 0 or crop.height == 0:
        issues.append("SPEC-CAP-08: caption bbox is empty on the phone proof")
        return issues
    dark = 0
    sand = 0
    for px in crop.getdata():
        y = luma_rgb(px)
        if y < 0.25:
            dark += 1
        if 0.75 <= y <= 0.98:
            sand += 1
    if sand == 0:
        issues.append("SPEC-CAP-08: sand fill is not visible at 25% scale")
    if dark == 0:
        issues.append("SPEC-CAP-08: stroke vanishes at 25% scale")
    return issues


def write_phone_proof(
    dest: Path,
    caption: Caption,
    underlay_path: str | Path | None = None,
) -> tuple[Path, list[str]]:
    dest.parent.mkdir(parents=True, exist_ok=True)
    base = _open_still(underlay_path)
    if base is None:
        base = Image.new("RGB", (CANVAS_W, CANVAS_H), (26, 20, 16))
    framed = draw_caption_card(base, caption)
    proof = framed.resize((PHONE_PROOF_W, PHONE_PROOF_H), Image.Resampling.LANCZOS)
    proof.save(dest, format="JPEG", quality=88)
    issues = phone_proof_issues(proof, caption)
    return dest, issues
