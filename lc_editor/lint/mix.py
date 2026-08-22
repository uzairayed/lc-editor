from __future__ import annotations

import math

from lc_editor.models import SFX_UNDER_BED_DB, Timeline


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
    if timeline.duck:
        peak = max(bed_lin, sfx_peak)
    else:
        peak = bed_lin + sfx_peak
    if peak <= 0:
        return -120.0
    return 20 * math.log10(peak)


def mix_issues(timeline: Timeline) -> list[str]:
    warnings: list[str] = []
    bed = 0.0 if timeline.bed_kind == "none" else timeline.bed_gain_db
    for sfx in timeline.sfx:
        if sfx_too_hot(sfx.gain_db, timeline.bed_gain_db, timeline.bed_kind):
            warnings.append(
                f"SPEC-SND-05: SFX {sfx.kind} at {sfx.gain_db} dB is not 6 dB under bed {bed} dB"
            )
    peak = estimate_true_peak_db(timeline)
    if peak > 0.0:
        warnings.append(f"SPEC-SND-09: true peak {peak:.2f} dBTP exceeds 0.0")
    return warnings
