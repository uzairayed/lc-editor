from __future__ import annotations

import math

from lc_editor.models import SFX_UNDER_BED_DB, TRUE_PEAK_LIMIT_DBTP, Timeline
from lc_editor.render.audio import resolve_denoise_profile


def sfx_too_hot(sfx_gain_db: float, bed_gain_db: float, bed_kind: str) -> bool:
    bed = 0.0 if bed_kind == "none" else bed_gain_db
    ceiling = bed - SFX_UNDER_BED_DB
    return sfx_gain_db > ceiling + 1e-9


def estimate_true_peak_db(timeline: Timeline) -> float:
    bed_db = 0.0 if timeline.bed_kind == "none" else timeline.bed_gain_db
    bed_lin = 10 ** (bed_db / 20)
    sfx_peak = 0.0
    for sfx in timeline.sfx:
        sfx_peak = max(sfx_peak, 10 ** (sfx.gain_db / 20))
    music_peak = 0.0
    for track in timeline.music:
        music_peak = max(music_peak, 10 ** (track.gain_db / 20))
    if timeline.duck or any(t.duck_natural for t in timeline.music):
        peak = max(bed_lin, sfx_peak, music_peak)
    else:
        peak = bed_lin + sfx_peak + music_peak
    if peak <= 0:
        return -120.0
    return 20 * math.log10(peak)


def estimate_post_peak_db(timeline: Timeline) -> float:
    pre = estimate_true_peak_db(timeline)
    return min(pre, TRUE_PEAK_LIMIT_DBTP)


def estimate_wind_band(timeline: Timeline) -> dict:
    outdoor = any(resolve_denoise_profile(clip, timeline) == "outdoor" for clip in timeline.clips)
    indoor = any(resolve_denoise_profile(clip, timeline) == "indoor" for clip in timeline.clips)
    bed_wind = timeline.bed_kind == "wind"
    pre_low = 1.0 if (outdoor or bed_wind or timeline.bed_kind != "none") else 0.2
    pre_high = 1.0 if (outdoor or bed_wind) else 0.2
    drop = 0.55 if outdoor or bed_wind else (0.35 if indoor else 0.0)
    return {
        "pre": {"hz_80_400": round(pre_low, 3), "hz_2000_8000": round(pre_high, 3)},
        "post": {
            "hz_80_400": round(pre_low * (1.0 - drop), 3),
            "hz_2000_8000": round(pre_high * (1.0 - drop * 0.8), 3),
        },
    }


def mix_preview_payload(timeline: Timeline) -> dict:
    pre = estimate_true_peak_db(timeline)
    post = estimate_post_peak_db(timeline)
    return {
        "true_peak_dbtp": post,
        "pre_peak_dbtp": pre,
        "post_peak_dbtp": post,
        "wind_band": estimate_wind_band(timeline),
    }


def mix_issues(timeline: Timeline) -> list[str]:
    warnings: list[str] = []
    bed = 0.0 if timeline.bed_kind == "none" else timeline.bed_gain_db
    for sfx in timeline.sfx:
        if sfx_too_hot(sfx.gain_db, timeline.bed_gain_db, timeline.bed_kind):
            warnings.append(
                f"SPEC-SND-05: SFX {sfx.kind} at {sfx.gain_db} dB is not 6 dB under bed {bed} dB"
            )
    post = estimate_post_peak_db(timeline)
    if post > TRUE_PEAK_LIMIT_DBTP + 1e-9:
        warnings.append(f"SPEC-SND-09: true peak {post:.2f} dBTP exceeds -1.0")
    return warnings
