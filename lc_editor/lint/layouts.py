from __future__ import annotations

from lc_editor.models import LAYOUT_PANE_COUNT, LEGAL_LAYOUTS, MediaItem, Timeline, is_layout_clip


def layout_issues(timeline: Timeline, media: list[MediaItem] | None = None) -> list[str]:
    errors: list[str] = []
    known = {item.id for item in (media or [])}
    for clip in timeline.clips:
        if not clip.layout and not clip.panes:
            continue
        if clip.layout and not clip.panes:
            errors.append(f"SPEC-LAYO-05: clip {clip.id} has a layout with no panes")
            continue
        if clip.panes and not clip.layout:
            errors.append(f"SPEC-LAYO-05: clip {clip.id} has panes without a layout kind")
            continue
        if not is_layout_clip(clip):
            continue
        if clip.layout not in LEGAL_LAYOUTS:
            errors.append(f"SPEC-LAYO-05: clip {clip.id} has unknown layout {clip.layout}")
            continue
        need = LAYOUT_PANE_COUNT[clip.layout]
        if len(clip.panes) != need:
            errors.append(f"SPEC-LAYO-05: clip {clip.id} {clip.layout} needs {need} panes")
        if media is not None:
            for i, pane in enumerate(clip.panes):
                if pane.media_id not in known:
                    errors.append(f"SPEC-LAYO-05: clip {clip.id} pane {i} references missing media {pane.media_id}")
    return errors
