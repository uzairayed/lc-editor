from __future__ import annotations

from pathlib import Path

from lc_editor.models import Caption, Timeline

YOUTUBE_MAX_DURATION_S = 12 * 60 * 60
YOUTUBE_UNVERIFIED_MAX_DURATION_S = 15 * 60
YOUTUBE_MAX_FILE_SIZE = 256 * 1024**3
HDR_TRANSFERS = frozenset({"arib-std-b67", "hlg", "smpte2084", "pq"})
HDR_PRIMARIES = frozenset({"bt2020"})


def srt_timestamp(seconds: float) -> str:
    millis = max(0, int(round(seconds * 1000)))
    hours, millis = divmod(millis, 3_600_000)
    minutes, millis = divmod(millis, 60_000)
    secs, millis = divmod(millis, 1000)
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{millis:03d}"


def youtube_srt(timeline: Timeline) -> str:
    starts = {clip.id: (clip.start_s, clip.duration_s) for clip in timeline.clips}
    rows: list[str] = []
    index = 1
    for caption in timeline.captions:
        timing = starts.get(caption.clip_id)
        if timing is None:
            continue
        clip_start, clip_duration = timing
        start = clip_start
        end = clip_start + min(clip_duration, max(0.2, caption.hold_s))
        if caption.words:
            start = clip_start + min(word.start_s for word in caption.words)
            end = clip_start + max(word.end_s for word in caption.words)
            end = min(clip_start + clip_duration, end)
        rows.extend(
            [
                str(index),
                f"{srt_timestamp(start)} --> {srt_timestamp(max(start + 0.2, end))}",
                _caption_text(caption),
                "",
            ]
        )
        index += 1
    return "\n".join(rows)


def write_youtube_srt(path: Path, timeline: Timeline) -> Path | None:
    body = youtube_srt(timeline)
    if not body:
        return None
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding="utf-8-sig", newline="\n")
    return path


def validate_youtube_metadata(
    *,
    title: str,
    description: str,
    chapters: list[dict] | None,
    duration_s: float,
) -> list[str]:
    errors: list[str] = []
    if len(title) > 100:
        errors.append("SPEC-EXPORT-11: YouTube title exceeds 100 characters")
    if len(description) > 5000:
        errors.append("SPEC-EXPORT-11: YouTube description exceeds 5000 characters")
    if chapters:
        parsed: list[tuple[float, str]] = []
        for chapter in chapters:
            try:
                at_s = float(chapter.get("at_s", -1))
            except (TypeError, ValueError, AttributeError):
                at_s = -1
            label = str(chapter.get("title", "")).strip() if isinstance(chapter, dict) else ""
            if at_s < 0 or at_s >= duration_s or not label:
                errors.append("SPEC-EXPORT-11: each chapter needs a title and an in-range at_s")
                continue
            parsed.append((at_s, label))
        if parsed:
            if abs(parsed[0][0]) > 1e-6:
                errors.append("SPEC-EXPORT-11: YouTube chapters must start at 0:00")
            if len(parsed) < 3:
                errors.append("SPEC-EXPORT-11: YouTube chapters require at least 3 entries")
            if parsed != sorted(parsed):
                errors.append("SPEC-EXPORT-11: YouTube chapters must be ordered")
            for (start, _), (end, _) in zip(parsed, parsed[1:], strict=False):
                if end - start < 10:
                    errors.append("SPEC-EXPORT-11: each YouTube chapter must be at least 10 seconds")
                    break
            if duration_s - parsed[-1][0] < 10:
                errors.append("SPEC-EXPORT-11: each YouTube chapter must be at least 10 seconds")
    return errors


def has_hdr_metadata(color_transfer: str, color_primaries: str) -> bool:
    return color_transfer.lower() in HDR_TRANSFERS or color_primaries.lower() in HDR_PRIMARIES


def _caption_text(caption: Caption) -> str:
    return "\n".join(caption.lines) if caption.lines else caption.text
