from __future__ import annotations

from lc_editor.models import BeatGrid, Clip, Timeline


def subdivision_step(grid: BeatGrid, subdivision: str) -> float:
    beat = 60.0 / max(grid.bpm, 1.0)
    if subdivision == "1/2":
        return beat / 2.0
    if subdivision == "1/4":
        return beat / 4.0
    return beat


def grid_times(grid: BeatGrid, subdivision: str, end_s: float) -> list[float]:
    if subdivision == "1" and grid.beats:
        return [t for t in grid.beats if 0 <= t <= end_s + 1e-6]
    step = subdivision_step(grid, subdivision)
    times = []
    t = grid.offset_s
    while t <= end_s + 1e-6:
        times.append(round(t, 4))
        t += step
    return times


def nearest(times: list[float], value: float) -> float:
    if not times:
        return value
    return min(times, key=lambda t: abs(t - value))


def _caption_floor(timeline: Timeline, clip: Clip) -> float:
    holds = [c.hold_s for c in timeline.captions if c.clip_id == clip.id]
    if not holds:
        return 0.0
    return max(holds)


def propose_beat_sync(
    timeline: Timeline,
    *,
    strength: float = 1.0,
    subdivision: str = "1",
    min_shot_s: float = 0.5,
    max_shot_s: float = 8.0,
    protected_ids: list[str] | None = None,
) -> dict:
    grid = timeline.beat_grid
    if grid is None:
        return {"ok": False, "proposal": [], "warnings": ["SPEC-SND-13: no beat grid"]}
    strength = max(0.0, min(1.0, strength))
    protected = set(protected_ids or [])
    end = max((c.start_s + c.duration_s for c in timeline.clips), default=0.0)
    music_offset = timeline.music[0].start_s - timeline.music[0].in_s if timeline.music else 0.0
    times = [t + music_offset for t in grid_times(grid, subdivision, end + 8.0)]
    proposal = []
    warnings = []
    new_clips = []
    t = 0.0
    for clip in timeline.clips:
        old_end = clip.start_s + clip.duration_s
        target_end = nearest(times, old_end)
        blended = old_end + (target_end - old_end) * strength
        duration = max(0.01, blended - t)
        floor = _caption_floor(timeline, clip)
        blocked = clip.id in protected or clip.protect
        if blocked:
            duration = clip.duration_s
            warnings.append(f"protected {clip.id}")
        elif duration < max(min_shot_s, floor) - 1e-6:
            duration = max(clip.duration_s, max(min_shot_s, floor))
            warnings.append(f"hold/min floor kept duration for {clip.id}")
        elif duration > max_shot_s + 1e-6:
            duration = min(clip.duration_s, max_shot_s)
            warnings.append(f"max shot kept duration for {clip.id}")
        duration = round(duration, 4)
        proposal.append(
            {
                "clip_id": clip.id,
                "from_duration_s": clip.duration_s,
                "to_duration_s": duration,
                "from_end_s": round(old_end, 4),
                "to_end_s": round(t + duration, 4),
            }
        )
        new_out = round(clip.in_s + duration, 4)
        new_clips.append(clip.model_copy(update={"duration_s": duration, "out_s": new_out, "start_s": round(t, 4)}))
        t += duration
    sfx_moves = []
    for sfx in timeline.sfx:
        snapped = nearest(times, sfx.at_s)
        at = sfx.at_s + (snapped - sfx.at_s) * strength
        sfx_moves.append({"id": sfx.id, "from_s": sfx.at_s, "to_s": round(at, 4)})
    return {
        "ok": True,
        "proposal": proposal,
        "sfx": sfx_moves,
        "warnings": warnings,
        "clips": new_clips,
    }


def apply_beat_sync(timeline: Timeline, preview: dict) -> Timeline:
    if not preview.get("ok"):
        from lc_editor.ops.timeline import Reject

        raise Reject(preview.get("warnings", ["SPEC-SND-13: invalid proposal"])[0])
    clips = preview["clips"]
    sfx_map = {row["id"]: row["to_s"] for row in preview.get("sfx", [])}
    sfx = [s.model_copy(update={"at_s": sfx_map.get(s.id, s.at_s)}) for s in timeline.sfx]
    return timeline.model_copy(update={"clips": clips, "sfx": sfx})
