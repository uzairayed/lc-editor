from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from lc_editor.fonts import face_for_caption, font_for, font_label, resolve_font, role_for_caption
from lc_editor.models import (
    contrast_is_lenient,
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
    canvas_wh,
    is_youtube_project,
    is_spoken_style,
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


def _font_at(role: str, size: int, font: str = "") -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    path = resolve_font(font, role=role if role in ("title", "body") else "body") if font else font_for(
        role if role in ("title", "body") else "body"
    )
    if path:
        try:
            return ImageFont.truetype(str(path), size)
        except OSError:
            pass
    return ImageFont.load_default()


def _measure(lines: list[str], role: str, size: int, font: str = "") -> tuple[float, float]:
    font_face = _font_at(role, size, font)
    widths: list[int] = []
    heights: list[int] = []
    for line in lines:
        box = font_face.getbbox(line or " ")
        widths.append(box[2] - box[0])
        heights.append(box[3] - box[1])
    width = max(widths) if widths else 0
    line_h = max(heights) if heights else size
    gap = int(size * 0.18)
    height = line_h * len(lines) + gap * max(0, len(lines) - 1)
    pad = _stroke_pad(role)
    return float(width + 2 * pad), float(height + 2 * pad)


def caption_geometry(project: Project | None = None) -> dict[str, int | float]:
    width, height = canvas_wh(project)
    if is_youtube_project(project) or width >= height:
        return {
            "width": width,
            "height": height,
            "safe_x0": round(width * 0.05),
            "safe_x1": round(width * 0.95),
            "safe_y0": round(height * 0.10),
            "safe_y1": round(height * 0.90),
            "band_y0": round(height * 0.10),
            "band_y1": round(height * 0.90),
            "box_width": round(width * 0.80),
            "y_min": 0.10,
            "y_max": 0.90,
        }
    return {
        "width": width,
        "height": height,
        "safe_x0": CAPTION_SAFE_X0,
        "safe_x1": CAPTION_SAFE_X1,
        "safe_y0": CAPTION_SAFE_Y0,
        "safe_y1": CAPTION_SAFE_Y1,
        "band_y0": CAPTION_BAND_Y0,
        "band_y1": CAPTION_BAND_Y1,
        "box_width": CAPTION_BOXW,
        "y_min": CAPTION_Y_MIN,
        "y_max": CAPTION_Y_MAX,
    }


def fontsize_for(caption: Caption, project: Project | None = None) -> int:
    lines = caption.lines or wrap_text(caption.text)
    base = base_fontsize(caption)
    role = role_for_caption(caption.style, caption.role, caption.font)
    box_width = int(caption_geometry(project)["box_width"])
    for size in range(base, CAPTION_SIZE_MIN - 1, -2):
        width, _ = _measure(lines, role, size, caption.font)
        if width <= box_width:
            return size
    return CAPTION_SIZE_MIN


def _font(caption: Caption, size: int | None = None) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    role = role_for_caption(caption.style, caption.role, caption.font)
    return _font_at(role, size or fontsize_for(caption), caption.font)


def estimate_bbox(caption: Caption, project: Project | None = None) -> dict:
    geometry = caption_geometry(project)
    lines = caption.lines or wrap_text(caption.text)
    size = fontsize_for(caption, project)
    role = role_for_caption(caption.style, caption.role, caption.font)
    width, height = _measure(lines, role, size, caption.font)
    cy = int(geometry["height"]) * caption.y_pct
    y0 = cy - height / 2
    y2 = cy + height / 2
    preferred_x0 = (int(geometry["width"]) - width) / 2
    if width <= int(geometry["box_width"]):
        x0 = min(
            max(preferred_x0, float(geometry["safe_x0"])),
            float(geometry["safe_x1"]) - width,
        )
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


def _open_still(
    path: str | Path | None,
    project: Project | None = None,
) -> Image.Image | None:
    if not path:
        return None
    src = Path(path)
    if not src.exists() or src.stat().st_size < 200:
        return None
    try:
        im = Image.open(src).convert("RGB")
    except OSError:
        return None
    canvas = canvas_wh(project)
    if im.size != canvas:
        im = im.resize(canvas)
    return im


def sample_underlay_luma(
    path: str | Path | None,
    bbox: dict,
    project: Project | None = None,
) -> float | None:
    im = _open_still(path, project)
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


def _protect_overlap(
    bbox: dict,
    clip: Clip | None,
    project: Project | None = None,
) -> bool:
    if clip is None or not clip.protect:
        return False
    width, height = canvas_wh(project)
    fx = clip.focus_x * width
    fy = clip.focus_y * height
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
    project: Project | None = None,
) -> list[str]:
    warnings: list[str] = []
    geometry = caption_geometry(project)
    style = caption.style if caption is not None else "phrase"
    pop = style == "pop"
    if box:
        warnings.append("SPEC-CRAFT-02: caption background is forbidden")
        warnings.append("SPEC-CAP-04: caption box is forbidden")
    if not pop and is_all_caps(text):
        warnings.append("SPEC-CAP-04: ALL CAPS is rejected; use sentence case")
    wrapped = lines if lines is not None else wrap_text(text)
    if not pop:
        if len(wrapped) > CAPTION_MAX_LINES:
            warnings.append("SPEC-CAP-02: caption wraps past 3 lines")
        if word_count(text) > CAPTION_MAX_WORDS:
            warnings.append("SPEC-CAP-02: caption exceeds ~16 words")
        if any(len(line) > CAPTION_LINE_MAX for line in wrapped):
            warnings.append("SPEC-CAP-02: wrapped line exceeds 28 characters")
        if any(line.strip() == "" for line in wrapped):
            warnings.append("SPEC-CAP-02: caption has an empty line")
    if y_pct < float(geometry["y_min"]) or y_pct > float(geometry["y_max"]):
        warnings.append(
            f"SPEC-CAP-03: caption Y outside "
            f"{float(geometry['y_min']) * 100:.0f}-{float(geometry['y_max']) * 100:.0f}% safe zone"
        )
    if not pop and clip is not None and wrapped and len(wrapped) <= CAPTION_MAX_LINES:
        need = hold_s(text, wrapped)
        if clip.duration_s + 1e-9 < need:
            warnings.append(
                f"SPEC-CAP-02: clip {clip.duration_s:.2f}s shorter than hold {need:.2f}s; "
                "extend the clip or drop the text"
            )
    if pop:
        return warnings
    probe = caption or Caption(
        id="tmp",
        clip_id=clip.id if clip else "c",
        text=text,
        role=role if role in ("title", "body") else "body",
        y_pct=y_pct,
        lines=wrapped,
    )
    bbox = estimate_bbox(probe, project)
    if (
        bbox["x"] < 0
        or bbox["y"] < 0
        or bbox["x2"] > int(geometry["width"])
        or bbox["y2"] > int(geometry["height"])
    ):
        warnings.append(
            f"SPEC-CAP-03: caption bbox clips the {geometry['width']}x{geometry['height']} frame; "
            "caption_move / wrap / smaller size. Never add a box."
        )
    if bbox["y"] < int(geometry["band_y0"]) or bbox["y2"] > int(geometry["band_y1"]):
        warnings.append(
            "SPEC-CAP-03: caption block leaves the 22-50% band; "
            "caption_move / wrap / smaller size. Never add a box."
        )
    if (
        bbox["x"] < int(geometry["safe_x0"])
        or bbox["y"] < int(geometry["safe_y0"])
        or bbox["y2"] > int(geometry["safe_y1"])
    ):
        warnings.append("SPEC-CAP-03: caption bbox leaves the cross-post safe rect")
    if bbox["x2"] > int(geometry["safe_x1"]):
        warnings.append(
            f"SPEC-CAP-03: caption bbox crosses the safe right edge "
            f"(x2 > {geometry['safe_x1']}); "
            "wrap / smaller size. Never add a box."
        )
    if _protect_overlap(bbox, clip, project):
        warnings.append("SPEC-CAP-03: caption overlaps a protected focus point")
    luma = sample_underlay_luma(underlay_path, bbox, project)
    if contrast_too_close(luma):
        warnings.append(
            "SPEC-CAP-06: underlay is too close to sand; caption_move to a darker band or recut. Never add a box."
        )
    return warnings


def caption_style_warnings(caption: Caption) -> list[str]:
    """Soft hints: spoken styles on process-length copy. Does not fail add."""
    style = caption.style
    if not is_spoken_style(style):
        return []
    text = caption.text
    n_words = word_count(text)
    wrapped = caption.lines or wrap_text(text)
    if style == "karaoke" and (n_words >= 8 or len(wrapped) >= 2):
        return [
            "SPEC-CAP-13: karaoke on a long process-style line; "
            "use style=card for product/process/ambient reels"
        ]
    timed = caption.words
    if style == "pop" and n_words >= 8 and len(timed) <= 3:
        return [
            "SPEC-CAP-13: pop on a long process-style line; "
            "use style=card for product/process/ambient reels"
        ]
    if style == "pop" and any(word_count(w.text) >= 3 for w in timed):
        return [
            "SPEC-CAP-13: pop on a long process-style line; "
            "use style=card for product/process/ambient reels"
        ]
    return []


def style_warnings(timeline: Timeline) -> list[str]:
    warnings: list[str] = []
    for cap in timeline.captions:
        warnings.extend(caption_style_warnings(cap))
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


def _is_cap06(msg: str) -> bool:
    return "SPEC-CAP-06" in msg


def timeline_caption_issues(
    timeline: Timeline,
    *,
    media: list[MediaItem] | None = None,
    project: Project | None = None,
) -> list[str]:
    """Hard caption failures for review/export. CAP-06 is soft when contrast is lenient."""
    clips = {c.id: c for c in timeline.clips}
    media_map = {m.id: m for m in (media or [])}
    issues: list[str] = []
    for cap in timeline.captions:
        clip = clips.get(cap.clip_id)
        item = media_map.get(clip.media_id) if clip else None
        issues.extend(
            caption_issues(
                cap.text,
                y_pct=cap.y_pct,
                clip=clip,
                lines=cap.lines,
                role=cap.role,
                underlay_path=item.path if item else None,
                caption=cap,
                project=project,
            )
        )
    if contrast_is_lenient(project):
        return [msg for msg in issues if not _is_cap06(msg)]
    return issues


def timeline_caption_warnings(
    timeline: Timeline,
    *,
    media: list[MediaItem] | None = None,
    project: Project | None = None,
) -> list[str]:
    """CAP-06 soft notes when contrast is lenient (process/ambient default)."""
    if not contrast_is_lenient(project):
        return []
    clips = {c.id: c for c in timeline.clips}
    media_map = {m.id: m for m in (media or [])}
    warns: list[str] = []
    for cap in timeline.captions:
        clip = clips.get(cap.clip_id)
        item = media_map.get(clip.media_id) if clip else None
        for msg in caption_issues(
            cap.text,
            y_pct=cap.y_pct,
            clip=clip,
            lines=cap.lines,
            role=cap.role,
            underlay_path=item.path if item else None,
            caption=cap,
            project=project,
        ):
            if _is_cap06(msg):
                warns.append(msg)
    return warns


def suggest_darker_y(
    text: str,
    *,
    clip: Clip | None,
    role: str,
    underlay_path: str | None,
    caption: Caption | None,
    y_pct: float,
) -> float | None:
    """Pick a darker in-band y when sand contrast fails."""
    best: float | None = None
    for y in (0.28, 0.32, 0.36, 0.40, 0.44, 0.48):
        if abs(y - y_pct) < 1e-6:
            continue
        probe = caption.model_copy(update={"y_pct": y}) if caption is not None else None
        issues = caption_issues(
            text,
            y_pct=y,
            clip=clip,
            role=role,
            underlay_path=underlay_path,
            caption=probe,
        )
        if any(_is_cap06(msg) for msg in issues):
            continue
        if best is None or abs(y - y_pct) < abs(best - y_pct):
            best = y
    return best


def card_report(
    caption: Caption,
    clip: Clip | None,
    media: MediaItem | None = None,
) -> dict:
    bbox = estimate_bbox(caption)
    luma = sample_underlay_luma(media.path if media else None, bbox)
    face = face_for_caption(caption.style, caption.role, caption.font)
    return {
        "id": caption.id,
        "hold_s": caption.hold_s,
        "lines": caption.lines or wrap_text(caption.text),
        "bbox": bbox,
        "contrast": {"luma": luma, "ok": not contrast_too_close(luma)},
        "enter": caption.enter,
        "role": caption.role,
        "style": caption.style,
        "font": caption.font or ("clash" if caption.style == "card" else ""),
        "font_label": font_label(face),
    }


def draw_caption_card(
    im: Image.Image,
    caption: Caption,
    project: Project | None = None,
) -> Image.Image:
    canvas = im.copy()
    draw = ImageDraw.Draw(canvas)
    size = fontsize_for(caption, project)
    font = _font(caption, size)
    lines = caption.lines or wrap_text(caption.text)
    bbox = estimate_bbox(caption, project)
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


def phone_proof_issues(
    proof: Image.Image,
    caption: Caption,
    project: Project | None = None,
) -> list[str]:
    issues: list[str] = []
    width, height = canvas_wh(project)
    expected = (max(1, width // 4), max(1, height // 4))
    if proof.size != expected:
        issues.append(f"SPEC-CAP-08: proof is not {expected[0]}x{expected[1]}")
        return issues
    bbox = estimate_bbox(caption, project)
    sx = proof.width / width
    sy = proof.height / height
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
    project: Project | None = None,
) -> tuple[Path, list[str]]:
    dest.parent.mkdir(parents=True, exist_ok=True)
    width, height = canvas_wh(project)
    base = _open_still(underlay_path, project)
    if base is None:
        base = Image.new("RGB", (width, height), (26, 20, 16))
    framed = draw_caption_card(base, caption, project)
    proof = framed.resize((max(1, width // 4), max(1, height // 4)), Image.Resampling.LANCZOS)
    proof.save(dest, format="JPEG", quality=88)
    issues = phone_proof_issues(proof, caption, project)
    return dest, issues
