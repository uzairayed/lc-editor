from __future__ import annotations

from math import ceil

from lc_editor.lint.captions import density_warnings, timeline_caption_issues
from lc_editor.lint.invariants import invariant_warnings, reject_duration
from lc_editor.lint.layers import layer_issues
from lc_editor.lint.mix import mix_issues
from lc_editor.models import (
    BEAT_CONFIDENCE_WARN,
    LOCKED_STILL_MAX_S,
    MAX_CLIPS_PER_60S,
    MUSIC_KINDS,
    SHOT_ACK_MIN_S,
    STILL_ACK_MIN_S,
    MediaItem,
    Project,
    Timeline,
    decorated_transition_count,
    timeline_duration,
)
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
    allow = bool(project and project.allow_music)
    if timeline.music and not allow:
        errors.append("SPEC-CRAFT-01: music is on the timeline while allow_music is false")
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


def _holds_whole_source(clip, source: MediaItem | None) -> bool:
    if source is None or source.kind == "image":
        return False
    return clip.in_s <= 1e-3 and abs(clip.duration_s - (source.duration_s or 0.0)) <= 0.05


def acknowledge_errors(
    timeline: Timeline,
    media: list[MediaItem] | None,
    *,
    allow_dense: bool = False,
) -> list[str]:
    errors: list[str] = []
    by_id = {item.id: item for item in (media or [])}
    for clip in timeline.clips:
        floor = STILL_ACK_MIN_S if clip.is_still else SHOT_ACK_MIN_S
        source = by_id.get(clip.media_id)
        if clip.duration_s + 1e-6 < floor and not _holds_whole_source(clip, source):
            errors.append(
                f"SPEC-EDIT-ACK-01: clip {clip.id} is {clip.duration_s:.2f}s (floor {floor:.2f}s)"
            )
    if not allow_dense:
        cap = max(1, ceil(timeline_duration(timeline) * MAX_CLIPS_PER_60S / 60.0))
        if len(timeline.clips) > cap:
            errors.append(f"SPEC-EDIT-ACK-02: {len(timeline.clips)} clips (cap {cap})")
    return errors


def acknowledge_warnings(timeline: Timeline, media: list[MediaItem] | None) -> list[str]:
    warnings: list[str] = []
    by_id = {item.id: item for item in (media or [])}
    for clip in timeline.clips:
        floor = STILL_ACK_MIN_S if clip.is_still else SHOT_ACK_MIN_S
        source = by_id.get(clip.media_id)
        if clip.duration_s + 1e-6 < floor and _holds_whole_source(clip, source):
            warnings.append(
                f"SPEC-EDIT-ACK-01: clip {clip.id} holds whole source {clip.duration_s:.2f}s"
            )
    return warnings


def review_blockers(
    timeline: Timeline,
    project: Project | None,
    media: list[MediaItem] | None = None,
    *,
    allow_dense: bool = False,
    lint_media: list[MediaItem] | None = None,
) -> list[str]:
    errors: list[str] = []
    errors.extend(timeline_caption_issues(timeline, media=lint_media if lint_media is not None else media, project=project))
    errors.extend(mix_issues(timeline))
    errors.extend(locked_still_issues(timeline))
    errors.extend(music_issues(timeline, project))
    errors.extend(layer_issues(timeline, media))
    errors.extend(decorated_transition_issues(timeline))
    errors.extend(wipe_graph_issues(timeline))
    errors.extend(acknowledge_errors(timeline, media, allow_dense=allow_dense))
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


def review_warnings(
    timeline: Timeline,
    project: Project | None = None,
    media: list[MediaItem] | None = None,
) -> list[str]:
    warns = [w for w in invariant_warnings(timeline) if "locked still" not in w]
    warns.extend(outdoor_denoise_warnings(timeline))
    warns.extend(density_warnings(timeline, project))
    warns.extend(acknowledge_warnings(timeline, media))
    if timeline.music:
        if any(not track.source_name.strip() for track in timeline.music):
            warns.append("SPEC-SND-15: music is present without source attribution")
        if any(track.gain_db > -3.0 for track in timeline.music):
            warns.append("SPEC-SND-15: music gain is hotter than -3 dB")
    if timeline.beat_grid and timeline.beat_grid.confidence < BEAT_CONFIDENCE_WARN:
        warns.append(f"SPEC-SND-13: beat grid confidence {timeline.beat_grid.confidence:.2f} is low")
    return warns
