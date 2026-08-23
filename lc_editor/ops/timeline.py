from __future__ import annotations

from lc_editor.models import (
    LEGAL_TRANSITIONS,
    SPEED_MAX,
    SPEED_MIN,
    Clip,
    MediaItem,
    Timeline,
    is_layout_clip,
    recompute_starts,
)


class Reject(ValueError):
    pass


def _clip_index(timeline: Timeline, clip_id: str) -> int:
    for i, clip in enumerate(timeline.clips):
        if clip.id == clip_id:
            return i
    raise Reject(f"unknown clip {clip_id}")


def add_clip(timeline: Timeline, clip: Clip) -> Timeline:
    clips = [*timeline.clips, clip]
    return recompute_starts(timeline.model_copy(update={"clips": clips}))


def remove_clip(timeline: Timeline, clip_id: str) -> Timeline:
    _clip_index(timeline, clip_id)
    clips = [c for c in timeline.clips if c.id != clip_id]
    captions = [c for c in timeline.captions if c.clip_id != clip_id]
    transitions = {k: v for k, v in timeline.transitions.items() if k != clip_id}
    return recompute_starts(
        timeline.model_copy(update={"clips": clips, "captions": captions, "transitions": transitions})
    )


def reorder_clip(timeline: Timeline, clip_id: str, index: int) -> Timeline:
    i = _clip_index(timeline, clip_id)
    clips = list(timeline.clips)
    clip = clips.pop(i)
    index = max(0, min(index, len(clips)))
    clips.insert(index, clip)
    return recompute_starts(timeline.model_copy(update={"clips": clips}))


def trim_clip(timeline: Timeline, clip_id: str, in_s: float, out_s: float, source: MediaItem) -> Timeline:
    if in_s < 0 or out_s <= in_s:
        raise Reject("SPEC-EDIT-05: invalid in/out")
    if out_s - 1e-9 > source.duration_s and not source.kind == "image":
        raise Reject("SPEC-EDIT-05: out past source duration")
    i = _clip_index(timeline, clip_id)
    clip = timeline.clips[i]
    duration = round(out_s - in_s, 4)
    clips = list(timeline.clips)
    update = {"in_s": in_s, "out_s": out_s, "duration_s": duration}
    if is_layout_clip(clip) and clip.panes:
        pane0 = clip.panes[0].model_copy(update={"in_s": in_s})
        update["panes"] = [pane0, *clip.panes[1:]]
    clips[i] = clip.model_copy(update=update)
    return recompute_starts(timeline.model_copy(update={"clips": clips}))


def ripple_trim_clip(timeline: Timeline, clip_id: str, edge: str, delta_s: float, source: MediaItem) -> Timeline:
    i = _clip_index(timeline, clip_id)
    clip = timeline.clips[i]
    in_s, out_s = clip.in_s, clip.out_s
    if edge == "in":
        in_s = round(in_s + delta_s, 4)
    elif edge == "out":
        out_s = round(out_s + delta_s, 4)
    else:
        raise Reject("SPEC-EDIT-06: edge must be in or out")
    return trim_clip(timeline, clip_id, in_s, out_s, source)


def split_clip(timeline: Timeline, clip_id: str, at_s: float, new_id: str) -> Timeline:
    i = _clip_index(timeline, clip_id)
    clip = timeline.clips[i]
    if is_layout_clip(clip):
        raise Reject("SPEC-LAYO-06: split is not legal on a layout clip")
    if at_s <= 0 or at_s >= clip.duration_s:
        raise Reject("SPEC-EDIT-07: split must be inside the clip")
    first_out = round(clip.in_s + at_s, 4)
    first = clip.model_copy(update={"out_s": first_out, "duration_s": round(at_s, 4)})
    second = clip.model_copy(
        update={
            "id": new_id,
            "in_s": first_out,
            "duration_s": round(clip.duration_s - at_s, 4),
        }
    )
    clips = list(timeline.clips)
    clips[i : i + 1] = [first, second]
    return recompute_starts(timeline.model_copy(update={"clips": clips}))


def set_duration_clip(timeline: Timeline, clip_id: str, duration_s: float, source: MediaItem) -> Timeline:
    if duration_s <= 0:
        raise Reject("SPEC-EDIT-08: duration must be positive")
    i = _clip_index(timeline, clip_id)
    clip = timeline.clips[i]
    source_span = max(0.01, source.duration_s if source.kind == "video" else duration_s)
    if duration_s <= (clip.out_s - clip.in_s) + 1e-9 or duration_s <= source_span + 1e-9:
        new_out = round(clip.in_s + duration_s, 4)
        update = {"duration_s": round(duration_s, 4), "out_s": new_out}
    else:
        update = {"duration_s": round(duration_s, 4), "out_s": round(clip.in_s + duration_s, 4)}
    clips = list(timeline.clips)
    clips[i] = clip.model_copy(update=update)
    return recompute_starts(timeline.model_copy(update={"clips": clips}))


def fit_clip(timeline: Timeline, clip_id: str, source: MediaItem) -> Timeline:
    caps = [c for c in timeline.captions if c.clip_id == clip_id]
    if not caps:
        raise Reject("SPEC-EDIT-09: no caption on clip")
    hold = max(c.hold_s for c in caps)
    return set_duration_clip(timeline, clip_id, hold, source)


def refocus_clip(timeline: Timeline, clip_id: str, x: float, y: float) -> Timeline:
    if not (0.0 <= x <= 1.0 and 0.0 <= y <= 1.0):
        raise Reject("SPEC-EDIT-10: focus must be in [0, 1]")
    i = _clip_index(timeline, clip_id)
    clips = list(timeline.clips)
    clip = clips[i]
    update = {"focus_x": x, "focus_y": y}
    if is_layout_clip(clip) and clip.panes:
        pane0 = clip.panes[0].model_copy(update={"focus_x": x, "focus_y": y})
        update["panes"] = [pane0, *clip.panes[1:]]
    clips[i] = clip.model_copy(update=update)
    return timeline.model_copy(update={"clips": clips})


def gain_clip(timeline: Timeline, clip_id: str, db: float) -> Timeline:
    i = _clip_index(timeline, clip_id)
    clips = list(timeline.clips)
    clips[i] = clips[i].model_copy(update={"gain_db": db})
    return timeline.model_copy(update={"clips": clips})


def mute_clip(timeline: Timeline, clip_id: str, muted: bool) -> Timeline:
    i = _clip_index(timeline, clip_id)
    clips = list(timeline.clips)
    clips[i] = clips[i].model_copy(update={"muted": muted})
    return timeline.model_copy(update={"clips": clips})


def set_motion(timeline: Timeline, clip_id: str, motion: str, amount: float | None = None) -> Timeline:
    if motion == "hold":
        motion = "none"
    if motion not in ("none", "kenburns", "punch"):
        raise Reject("SPEC-EDIT-12: motion must be none, kenburns, or punch")
    i = _clip_index(timeline, clip_id)
    clips = list(timeline.clips)
    update: dict = {"motion": motion}
    if amount is not None:
        update["kenburns_amount"] = amount
    clips[i] = clips[i].model_copy(update=update)
    return timeline.model_copy(update={"clips": clips})


def set_speed(timeline: Timeline, clip_id: str, rate: float) -> Timeline:
    i = _clip_index(timeline, clip_id)
    clip = timeline.clips[i]
    if clip.is_still:
        raise Reject("SPEC-FX: motion_speed is video only")
    if rate < SPEED_MIN or rate > SPEED_MAX:
        raise Reject(f"SPEC-FX: speed must be in {SPEED_MIN}-{SPEED_MAX}")
    clips = list(timeline.clips)
    clips[i] = clip.model_copy(update={"speed": rate})
    return timeline.model_copy(update={"clips": clips})


def set_wrap(timeline: Timeline, clip_id: str, wrap: str) -> Timeline:
    if wrap not in ("off", "soft"):
        raise Reject("SPEC-FX: wrap must be off or soft")
    i = _clip_index(timeline, clip_id)
    clips = list(timeline.clips)
    clips[i] = clips[i].model_copy(update={"wrap": wrap})
    return timeline.model_copy(update={"clips": clips})


def set_denoise(timeline: Timeline, clip_id: str, profile: str) -> Timeline:
    if profile not in ("off", "outdoor", "indoor", "auto"):
        raise Reject("SPEC-SND-10: profile must be off, outdoor, indoor, or auto")
    if clip_id == "all":
        clips = [c.model_copy(update={"denoise": profile}) for c in timeline.clips]
        return timeline.model_copy(update={"clips": clips})
    i = _clip_index(timeline, clip_id)
    clips = list(timeline.clips)
    clips[i] = clips[i].model_copy(update={"denoise": profile})
    return timeline.model_copy(update={"clips": clips})


def set_gate(timeline: Timeline, clip_id: str, enabled: bool) -> Timeline:
    if clip_id == "all":
        clips = [c.model_copy(update={"gate": enabled}) for c in timeline.clips]
        return timeline.model_copy(update={"clips": clips})
    i = _clip_index(timeline, clip_id)
    clips = list(timeline.clips)
    clips[i] = clips[i].model_copy(update={"gate": enabled})
    return timeline.model_copy(update={"clips": clips})


def set_audio_xfade(timeline: Timeline, ms: float) -> Timeline:
    if ms < 0:
        raise Reject("SPEC-TRN: audio xfade ms must be >= 0")
    return timeline.model_copy(update={"audio_xfade_ms": ms})


def set_transition(timeline: Timeline, clip_id: str, kind: str) -> Timeline:
    if kind not in LEGAL_TRANSITIONS:
        raise Reject("SPEC-EDIT-13: illegal transition")
    i = _clip_index(timeline, clip_id)
    last = i == len(timeline.clips) - 1
    if kind == "close_fade" and not last:
        raise Reject("SPEC-EDIT-13: close_fade is only legal on the last clip")
    transitions = dict(timeline.transitions)
    if kind == "hard":
        transitions.pop(clip_id, None)
    else:
        transitions[clip_id] = kind  # type: ignore[assignment]
    return timeline.model_copy(update={"transitions": transitions})


def protect_clip(timeline: Timeline, clip_id: str, enabled: bool, intensity: float | None = None) -> Timeline:
    i = _clip_index(timeline, clip_id)
    clips = list(timeline.clips)
    update: dict = {"protect": enabled}
    if enabled:
        update["grade_intensity"] = 0.40 if intensity is None else intensity
    elif intensity is not None:
        update["grade_intensity"] = intensity
    clips[i] = clips[i].model_copy(update=update)
    return timeline.model_copy(update={"clips": clips})
