from __future__ import annotations

from lc_editor.analysis.media import is_sub_720, resolution_label
from lc_editor.models import (
    CANVAS_1080_MIN,
    MediaItem,
    Project,
    SOURCE_SHORT_MIN,
    Timeline,
    clip_media_ids,
)

FIT_MODES = {"fit", "fit_blur", "fit_pad", "letterbox"}


def canvas_is_1080_class(project: Project | None) -> bool:
    if project is None:
        return True
    return min(project.width, project.height) >= CANVAS_1080_MIN


def clip_uses_cover(clip) -> bool:
    framing = getattr(clip, "fit", None) or getattr(clip, "fit_mode", None)
    if isinstance(framing, str) and framing.lower() in FIT_MODES:
        return False
    return True


def _visual_sources(clip, by_id: dict[str, MediaItem]) -> list[MediaItem]:
    out: list[MediaItem] = []
    for media_id in clip_media_ids(clip):
        item = by_id.get(media_id)
        if item is None or item.kind == "audio":
            continue
        out.append(item)
    return out


def _sub720_sources(clip, by_id: dict[str, MediaItem]) -> list[MediaItem]:
    return [item for item in _visual_sources(clip, by_id) if is_sub_720(item.width, item.height)]


def quality_blockers(
    timeline: Timeline,
    project: Project | None,
    media: list[MediaItem] | None,
) -> list[str]:
    """QLT-01 never hard-blocks export; soft sources are warnings only."""
    del timeline, project, media
    return []


def quality_warnings(
    timeline: Timeline,
    project: Project | None,
    media: list[MediaItem] | None,
) -> list[str]:
    by_id = {item.id: item for item in (media or [])}
    warns: list[str] = []
    for clip in timeline.clips:
        for item in _sub720_sources(clip, by_id):
            label = resolution_label(item.width, item.height)
            if clip_uses_cover(clip) and canvas_is_1080_class(project):
                warns.append(
                    f"SPEC-QLT-01: clip {clip.id} cover-upscales {label} into 1080 canvas "
                    f"(short side below {SOURCE_SHORT_MIN})"
                )
            else:
                warns.append(
                    f"SPEC-QLT-01: clip {clip.id} source {label} is below {SOURCE_SHORT_MIN} short side"
                )
    return warns
