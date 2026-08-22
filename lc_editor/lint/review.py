from __future__ import annotations

from lc_editor.lint.captions import timeline_caption_issues
from lc_editor.lint.invariants import invariant_warnings, reject_duration
from lc_editor.lint.mix import mix_issues
from lc_editor.models import LOCKED_STILL_MAX_S, MUSIC_KINDS, Project, Timeline


def locked_still_issues(timeline: Timeline) -> list[str]:
    errors: list[str] = []
    for clip in timeline.clips:
        if clip.is_still and clip.motion == "none" and clip.duration_s > LOCKED_STILL_MAX_S:
            errors.append(
                f"SPEC-CRAFT-05: clip {clip.id} is a locked still of {clip.duration_s:.2f}s (limit 1.40s)"
            )
    return errors


def music_issues(timeline: Timeline, project: Project | None) -> list[str]:
    errors: list[str] = []
    if project is not None and project.allow_music:
        errors.append("SPEC-CRAFT-01: allow_music is true")
    if timeline.bed_kind in MUSIC_KINDS:
        errors.append(f"SPEC-CRAFT-01: musical bed {timeline.bed_kind}")
    for sfx in timeline.sfx:
        if sfx.kind in MUSIC_KINDS or sfx.kind.startswith("music"):
            errors.append(f"SPEC-CRAFT-01: music SFX {sfx.kind}")
    return errors


def review_blockers(timeline: Timeline, project: Project | None) -> list[str]:
    errors: list[str] = []
    errors.extend(timeline_caption_issues(timeline))
    errors.extend(mix_issues(timeline))
    errors.extend(locked_still_issues(timeline))
    errors.extend(music_issues(timeline, project))
    cap = reject_duration(timeline)
    if cap:
        errors.append(cap)
    return errors


def review_warnings(timeline: Timeline) -> list[str]:
    return [w for w in invariant_warnings(timeline) if "locked still" not in w]
