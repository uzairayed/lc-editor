from __future__ import annotations

from lc_editor.models import (
    CAPTION_MAX_LINES,
    CAPTION_MAX_WORDS,
    CAPTION_WRAP,
    CAPTION_Y_MAX,
    CAPTION_Y_MIN,
    Caption,
    Clip,
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
    floor = 1.8 if len(lines) == 2 else 1.5
    raw = chars / 18 + 0.4
    return round(max(floor, raw), 2)


def caption_issues(
    text: str,
    *,
    y_pct: float,
    clip: Clip | None,
    box: bool = False,
    lines: list[str] | None = None,
) -> list[str]:
    warnings: list[str] = []
    if box:
        warnings.append("SPEC-CAP-07: caption background is forbidden")
    wrapped = lines if lines is not None else wrap_text(text)
    if len(wrapped) > CAPTION_MAX_LINES:
        warnings.append("SPEC-CAP-05: caption wraps past 2 lines")
    if word_count(text) > CAPTION_MAX_WORDS:
        warnings.append("SPEC-CAP-06: caption exceeds ~10 words")
    if y_pct < CAPTION_Y_MIN or y_pct > CAPTION_Y_MAX:
        warnings.append("SPEC-CAP-09: caption Y outside 22-50% safe zone")
    if clip is not None and wrapped and len(wrapped) <= CAPTION_MAX_LINES:
        need = hold_s(text, wrapped)
        if clip.duration_s + 1e-9 < need:
            warnings.append(
                f"SPEC-CAP-11: clip {clip.duration_s:.2f}s shorter than hold {need:.2f}s; "
                "extend the clip or drop the text"
            )
    return warnings


def timeline_caption_issues(timeline: Timeline) -> list[str]:
    clips = {c.id: c for c in timeline.clips}
    warnings: list[str] = []
    for cap in timeline.captions:
        clip = clips.get(cap.clip_id)
        warnings.extend(
            caption_issues(cap.text, y_pct=cap.y_pct, clip=clip, lines=cap.lines)
        )
    return warnings
