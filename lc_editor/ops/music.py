from __future__ import annotations

from lc_editor.models import BeatGrid, MusicTrack, Timeline
from lc_editor.ops.timeline import Reject


def add_music(timeline: Timeline, track: MusicTrack, *, allow_music: bool) -> Timeline:
    if not allow_music:
        raise Reject("SPEC-MUS-02: allow_music is false")
    if track.duration_s <= 0:
        raise Reject("SPEC-SND-11: music duration must be positive")
    return timeline.model_copy(update={"music": [*timeline.music, track]})


def update_music(timeline: Timeline, track_id: str, **fields) -> Timeline:
    for i, track in enumerate(timeline.music):
        if track.id != track_id:
            continue
        allowed = {
            "start_s",
            "in_s",
            "duration_s",
            "gain_db",
            "fade_in_s",
            "fade_out_s",
            "loop",
            "duck_natural",
            "source_name",
            "license_note",
        }
        update = {k: v for k, v in fields.items() if v is not None and k in allowed}
        tracks = list(timeline.music)
        tracks[i] = track.model_copy(update=update)
        return timeline.model_copy(update={"music": tracks})
    raise Reject(f"unknown music {track_id}")


def remove_music(timeline: Timeline, track_id: str) -> Timeline:
    if not any(t.id == track_id for t in timeline.music):
        raise Reject(f"unknown music {track_id}")
    tracks = [t for t in timeline.music if t.id != track_id]
    grid = None if timeline.beat_grid and all(t.media_id != timeline.beat_grid.media_id for t in tracks) else timeline.beat_grid
    return timeline.model_copy(update={"music": tracks, "beat_grid": grid})


def set_beat_grid(timeline: Timeline, grid: BeatGrid) -> Timeline:
    if grid.bpm <= 0:
        raise Reject("SPEC-SND-13: bpm must be > 0")
    beats = list(grid.beats)
    if not beats:
        step = 60.0 / grid.bpm
        t = grid.offset_s
        end = 60.0
        if timeline.music:
            end = max(t.duration_s for t in timeline.music) + 1.0
        while t <= end:
            beats.append(round(t, 4))
            t += step
        grid = grid.model_copy(update={"beats": beats})
    return timeline.model_copy(update={"beat_grid": grid})
