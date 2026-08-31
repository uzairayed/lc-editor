from __future__ import annotations

from math import ceil

from lc_editor.lint.captions import density_warnings, timeline_caption_issues
from lc_editor.lint.invariants import invariant_warnings, reject_duration
from lc_editor.lint.layers import layer_issues
from lc_editor.lint.layouts import layout_issues
from lc_editor.lint.mix import mix_issues
from lc_editor.models import (
    BEAT_CONFIDENCE_WARN,
    LOCKED_STILL_MAX_S,
    MAX_CLIPS_PER_60S,
    MUSIC_KINDS,
    SHOT_ACK_MIN_S,
    STILL_ACK_MIN_S,
    ZOOM_PAIR_MIN_CLIP_S,
    ZOOM_SUGGEST_SKIP_S,
    MediaItem,
    Project,
    Timeline,
    decorated_transition_count,
    timeline_duration,
)
from lc_editor.assets.pack import sfx_manifest
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


def zoom_pair_issues(timeline: Timeline) -> list[str]:
    if not timeline.clips:
        return []
    last_id = timeline.clips[-1].id
    errors: list[str] = []
    for clip in timeline.clips:
        if clip.motion == "zoom_in" and clip.id != last_id:
            errors.append(f"SPEC-RND-20: clip {clip.id} has zoom_in with no matching zoom_out")
    return errors


def zoom_suggestions(timeline: Timeline) -> list[dict]:
    rows: list[dict] = []
    prev_pair = False
    pairs = 0
    dur = timeline_duration(timeline)
    budget = max(1, int(dur * 3 / 60.0 + 0.999)) if dur else 1
    for clip in timeline.clips:
        reasons: list[str] = []
        action = "none"
        if clip.duration_s < ZOOM_SUGGEST_SKIP_S:
            reasons.append("clip shorter than 2.5s")
        elif clip.protect:
            reasons.append("protect/face margin at 1.10")
        elif clip.is_still and clip.start_s < 1.2:
            reasons.append("open still kenburns")
        elif clip.duration_s + 1e-9 < ZOOM_PAIR_MIN_CLIP_S:
            reasons.append("clip shorter than 3.5s")
        elif prev_pair:
            reasons.append("previous clip is a pair")
        elif pairs >= budget:
            reasons.append("pair budget")
        else:
            action = "pair"
            reasons.append("stable clip with room for in/hold/out")
        rows.append(
            {
                "clip_id": clip.id,
                "action": action,
                "at_s": round(0.15 * clip.duration_s, 3) if action == "pair" else None,
                "reason": reasons,
            }
        )
        prev_pair = action == "pair"
        if action == "pair":
            pairs += 1
    return rows


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
    errors.extend(layout_issues(timeline, media))
    errors.extend(decorated_transition_issues(timeline))
    errors.extend(wipe_graph_issues(timeline))
    errors.extend(zoom_pair_issues(timeline))
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
    licenses = {item["kind"]: str(item.get("license") or "").strip() for item in sfx_manifest()}
    seen_sfx: set[str] = set()
    for sfx in timeline.sfx:
        if sfx.kind in seen_sfx:
            continue
        seen_sfx.add(sfx.kind)
        if not licenses.get(sfx.kind):
            warns.append(f"SPEC-SND-02: SFX {sfx.kind} has no license")
    if timeline.beat_grid and timeline.beat_grid.confidence < BEAT_CONFIDENCE_WARN:
        warns.append(f"SPEC-SND-13: beat grid confidence {timeline.beat_grid.confidence:.2f} is low")
    return warns
