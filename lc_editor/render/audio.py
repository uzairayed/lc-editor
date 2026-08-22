from __future__ import annotations

from pathlib import Path

from lc_editor.models import TRUE_PEAK_LIMIT_DBTP, Clip, Timeline


def highpass_filter(hz: float) -> str:
    return f"highpass=f={hz}"


def resolve_denoise_profile(clip: Clip, timeline: Timeline) -> str:
    if clip.muted:
        return "off"
    profile = clip.denoise
    if profile == "auto":
        return "indoor" if timeline.bed_kind == "room" else "outdoor"
    return profile


def denoise_chain(profile: str, *, gated: bool = True, highpass_hz: float | None = None) -> str:
    if profile == "off":
        return ""
    if profile == "indoor":
        hp = 80.0 if highpass_hz is None else highpass_hz
        nr = 6
    else:
        hp = 120.0 if highpass_hz is None else highpass_hz
        nr = 12
    parts = [highpass_filter(hp), f"afftdn=nr={nr}"]
    if gated:
        parts.append("agate=attack=10:release=200")
    return ",".join(parts)


def limiter_filter() -> str:
    limit = 10 ** (TRUE_PEAK_LIMIT_DBTP / 20)
    return f"alimiter=limit={limit:.5f}:level=false"


def loudnorm_hero() -> str:
    return "loudnorm=I=-16:TP=-1.5:LRA=8"


def hard_cut_audio_xfade(ms: float) -> str:
    if ms <= 0:
        return "anull"
    return f"acrossfade=d={ms / 1000.0}:c1=tri:c2=tri"


def j_cut_audio(frames: int = 10, fps: int = 30) -> str:
    lead = frames / fps
    return f"atrim=start=0,asetpts=PTS-STARTPTS,afade=t=in:st=0:d={lead:.4f}"


def l_cut_audio(frames: int = 10, fps: int = 30) -> str:
    hang = frames / fps
    return f"apad=pad_dur={hang:.4f}"


def transition_audio(kind: str, xfade_ms: float = 10.0, frames: int = 10) -> str:
    if kind == "j_cut":
        return j_cut_audio(frames)
    if kind == "l_cut":
        return l_cut_audio(frames)
    if kind == "hard":
        return hard_cut_audio_xfade(xfade_ms)
    return hard_cut_audio_xfade(xfade_ms)


def mix_graph(timeline: Timeline, *, include_limiter: bool = True) -> str:
    parts = []
    for clip in timeline.clips:
        profile = resolve_denoise_profile(clip, timeline)
        chain = denoise_chain(profile, gated=clip.gate, highpass_hz=timeline.highpass_hz)
        if chain:
            parts.append(chain)
    if timeline.bed_kind not in ("none",):
        bed_profile = "indoor" if timeline.bed_kind == "room" else "outdoor"
        parts.append(denoise_chain(bed_profile, gated=True, highpass_hz=timeline.highpass_hz))
    if include_limiter:
        parts.append(limiter_filter())
    graph = ",".join(p for p in parts if p)
    return graph


def sfx_mix_filter(timeline: Timeline, bed_path: Path | None, sfx_paths: list[tuple[Path, float, float]]) -> str:
    filters: list[str] = []
    idx = 0
    if bed_path:
        profile = "indoor" if timeline.bed_kind == "room" else "outdoor"
        den = denoise_chain(profile, gated=True, highpass_hz=timeline.highpass_hz)
        extra = f",{den}" if den else ""
        filters.append(f"[{idx}:a]volume={timeline.bed_gain_db}dB{extra}[bed]")
        idx += 1
    labels = []
    for i, (_path, at_s, gain) in enumerate(sfx_paths):
        filters.append(f"[{idx}:a]volume={gain}dB,adelay={int(at_s * 1000)}:all=1[s{i}]")
        labels.append(f"[s{i}]")
        idx += 1
    inputs = ("[bed]" if bed_path else "") + "".join(labels)
    n = (1 if bed_path else 0) + len(sfx_paths)
    if n == 0:
        return limiter_filter()
    if n == 1:
        body = ",".join(part.split("]", 1)[-1].rsplit("[", 1)[0] for part in filters[:1]) or "anull"
        return f"{body},{limiter_filter()}"
    filters.append(f"{inputs}amix=inputs={n}:normalize=0,{limiter_filter()}[aout]")
    return ";".join(filters)


def bed_asset_name(kind: str) -> str:
    return {"wind": "wind.wav", "room": "room.wav"}.get(kind, "")
