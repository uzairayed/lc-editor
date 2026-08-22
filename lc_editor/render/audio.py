from __future__ import annotations

from pathlib import Path

from lc_editor.models import Timeline
from lc_editor.render.paths import ffmpeg_path


def highpass_filter(hz: float) -> str:
    return f"highpass=f={hz}"


def sfx_mix_filter(timeline: Timeline, bed_path: Path | None, sfx_paths: list[tuple[Path, float, float]]) -> str:
    filters: list[str] = []
    idx = 0
    if bed_path:
        hp = f",{highpass_filter(timeline.highpass_hz)}" if timeline.highpass_hz else ""
        filters.append(f"[{idx}:a]volume={timeline.bed_gain_db}dB{hp}[bed]")
        idx += 1
    labels = []
    for i, (_path, at_s, gain) in enumerate(sfx_paths):
        filters.append(f"[{idx}:a]volume={gain}dB,adelay={int(at_s * 1000)}:all=1[s{i}]")
        labels.append(f"[s{i}]")
        idx += 1
    inputs = ("[bed]" if bed_path else "") + "".join(labels)
    n = (1 if bed_path else 0) + len(sfx_paths)
    if n == 0:
        return "anull"
    if n == 1:
        return ",".join(part.split("]", 1)[-1].rsplit("[", 1)[0] for part in filters[:1]) or "anull"
    filters.append(f"{inputs}amix=inputs={n}:normalize=0[aout]")
    return ";".join(filters)


def bed_asset_name(kind: str) -> str:
    return {"wind": "wind.wav", "room": "room.wav"}.get(kind, "")
