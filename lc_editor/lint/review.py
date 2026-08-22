from __future__ import annotations

from lc_editor.lint.captions import density_warnings, timeline_caption_issues
from lc_editor.lint.invariants import invariant_warnings, reject_duration
from lc_editor.lint.mix import mix_issues
from lc_editor.models import LOCKED_STILL_MAX_S, MUSIC_KINDS, MediaItem, Project, Timeline, decorated_transition_count
from lc_editor.render.transitions import banned_transition, graph_has_wipe, transition_video


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


def decorated_transition_issues(timeline: Timeline) -> list[str]:
    count = decorated_transition_count(timeline)
    if count > 3:
        return [f"SPEC-EDIT-13: {count} decorated transitions (cap 3)"]
    return []


def wipe_graph_issues(timeline: Timeline) -> list[str]:
    errors: list[str] = []
    for kind in timeline.transitions.values():
        if banned_transition(kind) or graph_has_wipe(transition_video(kind)):
            errors.append("SPEC-RND-03: wipe in graph")
            break
    return errors


def review_blockers(
    timeline: Timeline,
    project: Project | None,
    media: list[MediaItem] | None = None,
) -> list[str]:
    errors: list[str] = []
    errors.extend(timeline_caption_issues(timeline, media=media, project=project))
    errors.extend(mix_issues(timeline))
    errors.extend(locked_still_issues(timeline))
    errors.extend(music_issues(timeline, project))
    errors.extend(decorated_transition_issues(timeline))
    errors.extend(wipe_graph_issues(timeline))
    cap = reject_duration(timeline)
    if cap:
        errors.append(cap)
    return errors


def outdoor_denoise_warnings(timeline: Timeline) -> list[str]:
    warnings: list[str] = []
    audible_outdoor = timeline.bed_kind == "wind"
    for clip in timeline.clips:
        if clip.muted or clip.denoise != "off":
            continue
        if audible_outdoor:
            warnings.append(f"SPEC-SND-10: clip {clip.id} has denoise=off on outdoor/wind audio")
    return warnings


def review_warnings(timeline: Timeline, project: Project | None = None) -> list[str]:
    warns = [w for w in invariant_warnings(timeline) if "locked still" not in w]
    warns.extend(outdoor_denoise_warnings(timeline))
    warns.extend(density_warnings(timeline, project))
    return warns
