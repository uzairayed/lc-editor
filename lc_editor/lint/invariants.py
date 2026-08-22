from __future__ import annotations

from lc_editor.models import (
    DURATION_CAP_S,
    DURATION_SOFT_MAX_S,
    DURATION_SOFT_MIN_S,
    Timeline,
    decorated_transition_count,
    timeline_duration,
)


def reject_duration(timeline: Timeline) -> str | None:
    dur = timeline_duration(timeline)
    if dur > DURATION_CAP_S + 1e-9:
        return f"SPEC-EDIT-14: duration {dur:.2f}s exceeds cap 45.00s"
    return None


def invariant_warnings(timeline: Timeline) -> list[str]:
    warnings: list[str] = []
    dur = timeline_duration(timeline)
    if timeline.clips and dur > DURATION_SOFT_MAX_S:
        warnings.append(f"SPEC-EDIT-15: duration {dur:.2f}s is over 28.00s target")
    if timeline.clips and dur < DURATION_SOFT_MIN_S:
        warnings.append(f"SPEC-EDIT-15: duration {dur:.2f}s is under 15.00s target")
    decorated = decorated_transition_count(timeline)
    if decorated > 3:
        warnings.append(f"SPEC-EDIT-13: {decorated} decorated transitions (2-3 per reel)")
    for clip in timeline.clips:
        if clip.is_still and clip.motion == "none" and clip.duration_s >= 3.0:
            warnings.append(f"SPEC-EDIT-12: clip {clip.id} is a locked still of {clip.duration_s:.2f}s")
    t = 0.0
    for clip in timeline.clips:
        if abs(clip.start_s - t) > 1e-6:
            warnings.append("SPEC-EDIT-01: gap detected in timeline")
            break
        t += clip.duration_s
    return warnings
