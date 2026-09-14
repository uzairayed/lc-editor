from __future__ import annotations

from math import ceil
from pathlib import Path

from lc_editor.lint.captions import (
    density_warnings,
    style_warnings,
    timeline_caption_issues,
    timeline_caption_warnings,
)
from lc_editor.lint.invariants import invariant_warnings, reject_duration
from lc_editor.lint.layers import layer_issues
from lc_editor.lint.layouts import layout_issues
from lc_editor.lint.mix import mix_issues
from lc_editor.lint.provenance import provenance_warnings
from lc_editor.lint.quality import quality_blockers, quality_warnings
from lc_editor.models import (
    BEAT_CONFIDENCE_WARN,
    LOCKED_STILL_MAX_S,
    MAX_CLIPS_PER_60S,
    MIN_VIDEO_DURATION_S,
    MUSIC_KINDS,
    SHOT_ACK_MIN_S,
    STILL_ACK_MIN_S,
    ZOOM_PAIR_MIN_CLIP_S,
    ZOOM_SUGGEST_SKIP_S,
    Clip,
    MediaItem,
    Project,
    Timeline,
    decorated_transition_count,
    is_youtube_project,
    resolved_min_video_duration_s,
    timeline_duration,
)
from lc_editor.assets.pack import sfx_manifest
from lc_editor.assets.user_sfx import attribution_by_kind, find_user_sfx
from lc_editor.render.transitions import banned_transition, graph_has_wipe, transition_video


def locked_still_issues(timeline: Timeline) -> list[str]:
    """SPEC-CRAFT-05 soft warn for motion_none stills over 1.40s.

    Process cards may hold stills ~2-3s. SPEC-EDIT-ACK-01 still requires
    stills >= 2.20s. Ken Burns remains the default; locked stills warn
    instead of blocking review/export.
    """
    warnings: list[str] = []
    for clip in timeline.clips:
        if clip.is_still and clip.motion == "none" and clip.duration_s > LOCKED_STILL_MAX_S:
            warnings.append(
                f"SPEC-CRAFT-05: clip {clip.id} is a locked still of {clip.duration_s:.2f}s "
                f"(prefer kenburns/punch; process cards may hold ~2-3s)"
            )
    return warnings


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


def decorated_transition_issues(
    timeline: Timeline,
    project: Project | None = None,
) -> list[str]:
    count = decorated_transition_count(timeline)
    duration = timeline_duration(timeline)
    cap = max(3, ceil(duration / 60) * 3) if is_youtube_project(project) else 3
    if count > cap:
        return [f"SPEC-EDIT-13: {count} decorated transitions (cap {cap})"]
    return []


def wipe_graph_issues(timeline: Timeline) -> list[str]:
    errors: list[str] = []
    for kind in timeline.transitions.values():
        if banned_transition(kind) or graph_has_wipe(transition_video(kind)):
            errors.append("SPEC-RND-03: wipe in graph")
            break
    return errors


def holds_whole_source(in_s: float, duration_s: float, source: MediaItem | None) -> bool:
    if source is None or source.kind == "image":
        return False
    return in_s <= 1e-3 and abs(duration_s - (source.duration_s or 0.0)) <= 0.05


def _holds_whole_source(clip, source: MediaItem | None) -> bool:
    return holds_whole_source(clip.in_s, clip.duration_s, source)


def clip_exempt_from_video_floor(clip: Clip, source: MediaItem | None) -> bool:
    if clip.is_still:
        return True
    if source is not None and source.kind == "image":
        return True
    return False


def video_floor_reject(
    clip: Clip,
    source: MediaItem | None,
    duration_s: float,
    project: Project | None,
    *,
    in_s: float | None = None,
) -> str | None:
    if clip_exempt_from_video_floor(clip, source):
        return None
    floor = resolved_min_video_duration_s(project)
    if duration_s + 1e-6 >= floor:
        return None
    start = clip.in_s if in_s is None else in_s
    if holds_whole_source(start, duration_s, source):
        return None
    return (
        f"SPEC-EDIT-25: clip {clip.id} is {duration_s:.2f}s (video floor {floor:.2f}s)"
    )


def video_duration_floor_errors(
    timeline: Timeline,
    project: Project | None,
    media: list[MediaItem] | None,
) -> list[str]:
    errors: list[str] = []
    by_id = {item.id: item for item in (media or [])}
    for clip in timeline.clips:
        source = by_id.get(clip.media_id)
        err = video_floor_reject(clip, source, clip.duration_s, project)
        if err:
            errors.append(err)
    return errors


def video_duration_floor_warnings(
    timeline: Timeline,
    project: Project | None,
    media: list[MediaItem] | None,
) -> list[str]:
    warnings: list[str] = []
    by_id = {item.id: item for item in (media or [])}
    floor = resolved_min_video_duration_s(project)
    for clip in timeline.clips:
        source = by_id.get(clip.media_id)
        if clip_exempt_from_video_floor(clip, source):
            continue
        if clip.duration_s + 1e-6 >= floor:
            continue
        if _holds_whole_source(clip, source):
            warnings.append(
                f"SPEC-EDIT-25: clip {clip.id} holds whole source {clip.duration_s:.2f}s "
                f"(video floor {floor:.2f}s)"
            )
    return warnings


def resolve_density_allow(
    project: Project | None,
    allow_dense: bool | None = None,
) -> tuple[bool, str | None]:
    if allow_dense is True:
        return True, "allow_dense"
    if allow_dense is False:
        return False, None
    if resolved_min_video_duration_s(project) >= MIN_VIDEO_DURATION_S:
        return True, "min_video_duration_s"
    return False, None


def acknowledge_errors(
    timeline: Timeline,
    media: list[MediaItem] | None,
    *,
    allow_dense: bool | None = None,
    project: Project | None = None,
) -> list[str]:
    errors: list[str] = []
    by_id = {item.id: item for item in (media or [])}
    for clip in timeline.clips:
        floor = (
            0.5
            if is_youtube_project(project)
            else (STILL_ACK_MIN_S if clip.is_still else SHOT_ACK_MIN_S)
        )
        source = by_id.get(clip.media_id)
        if clip.duration_s + 1e-6 < floor and not _holds_whole_source(clip, source):
            errors.append(
                f"SPEC-EDIT-ACK-01: clip {clip.id} is {clip.duration_s:.2f}s (floor {floor:.2f}s)"
            )
    allowed, _ = resolve_density_allow(project, allow_dense)
    if not allowed:
        cap = max(1, ceil(timeline_duration(timeline) * MAX_CLIPS_PER_60S / 60.0))
        if len(timeline.clips) > cap:
            errors.append(f"SPEC-EDIT-ACK-02: {len(timeline.clips)} clips (cap {cap})")
    return errors


def acknowledge_warnings(
    timeline: Timeline,
    media: list[MediaItem] | None,
    project: Project | None = None,
) -> list[str]:
    if is_youtube_project(project):
        return []
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
    allow_dense: bool | None = None,
    lint_media: list[MediaItem] | None = None,
) -> list[str]:
    errors: list[str] = []
    errors.extend(timeline_caption_issues(timeline, media=lint_media if lint_media is not None else media, project=project))
    errors.extend(mix_issues(timeline))
    errors.extend(music_issues(timeline, project))
    errors.extend(layer_issues(timeline, media))
    errors.extend(layout_issues(timeline, media))
    errors.extend(decorated_transition_issues(timeline, project))
    errors.extend(wipe_graph_issues(timeline))
    errors.extend(zoom_pair_issues(timeline))
    errors.extend(acknowledge_errors(timeline, media, allow_dense=allow_dense, project=project))
    errors.extend(quality_blockers(timeline, project, media))
    errors.extend(video_duration_floor_errors(timeline, project, media))
    cap = reject_duration(timeline, project)
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
    user_sfx_dir: Path | None = None,
    understand_spans: dict[str, list] | None = None,
    shot_cards=None,
    shots_by_media=None,
) -> list[str]:
    warns = [w for w in invariant_warnings(timeline, project) if "locked still" not in w]
    warns.extend(locked_still_issues(timeline))
    warns.extend(timeline_caption_warnings(timeline, media=media, project=project))
    warns.extend(outdoor_denoise_warnings(timeline))
    warns.extend(density_warnings(timeline, project))
    warns.extend(style_warnings(timeline))
    warns.extend(acknowledge_warnings(timeline, media, project))
    warns.extend(quality_warnings(timeline, project, media))
    warns.extend(video_duration_floor_warnings(timeline, project, media))
    if timeline.music:
        if any(not track.source_name.strip() for track in timeline.music):
            warns.append("SPEC-SND-15: music is present without source attribution")
        if any(track.gain_db > -3.0 for track in timeline.music):
            warns.append("SPEC-SND-15: music gain is hotter than -3 dB")
    licenses = {item["kind"]: str(item.get("license") or "").strip() for item in sfx_manifest()}
    bundled = set(licenses)
    attrs = attribution_by_kind(user_sfx_dir) if user_sfx_dir is not None else {}
    for kind, meta in attrs.items():
        lic = str(meta.get("license") or "").strip()
        if lic:
            licenses[kind] = lic
    seen_sfx: set[str] = set()
    for sfx in timeline.sfx:
        if sfx.kind in seen_sfx:
            continue
        seen_sfx.add(sfx.kind)
        if user_sfx_dir is not None and find_user_sfx(user_sfx_dir, sfx.kind):
            if sfx.kind not in attrs and sfx.kind not in bundled:
                licenses[sfx.kind] = ""
        if not licenses.get(sfx.kind):
            warns.append(f"SPEC-SND-02: SFX {sfx.kind} has no license")
    if timeline.beat_grid and timeline.beat_grid.confidence < BEAT_CONFIDENCE_WARN:
        warns.append(f"SPEC-SND-13: beat grid confidence {timeline.beat_grid.confidence:.2f} is low")
    if media and any(not item.captured_at for item in media):
        warns.append("media missing captured_at")
    warns.extend(
        provenance_warnings(
            timeline,
            media,
            understand_spans=understand_spans,
            shot_cards=shot_cards,
            shots_by_media=shots_by_media,
        )
    )
    return warns
