"""LENS-lite spatial densify (Train D).

When a span is high-value but spatially ambiguous (busy frame / low subject
dominance), densify keyframes inside the span and soft-suggest cover
``focus_x`` / ``focus_y``. PIL edge-energy tiles only. No VLM weights.
"""

from __future__ import annotations

import math
from pathlib import Path

from lc_editor.analysis.understand import refine_windows

GRID = 3
DEFAULT_SPATIAL_BUDGET = 12
MIN_SPATIAL_BUDGET = 4
MAX_SPATIAL_BUDGET = 32

# Low concentration + high tile entropy ≈ busy / multi-subject frame.
# Concentration is Herfindahl (sum p^2); uniform 3x3 ≈ 0.11, single-tile ≈ 1.0.
DOMINANCE_AMBIGUOUS_MAX = 0.22
ENTROPY_AMBIGUOUS_MIN = 0.72
HIGH_VALUE_SCORE_FLOOR = 0.35
HIGH_VALUE_TOP_FRAC = 0.4
FOCUS_DRIFT_WARN = 0.12
DEFAULT_FOCUS = 0.5


def clamp_spatial_budget(budget_frames: int | None, default: int = DEFAULT_SPATIAL_BUDGET) -> int:
    if budget_frames is None:
        return default
    try:
        value = int(budget_frames)
    except (TypeError, ValueError):
        return default
    return max(MIN_SPATIAL_BUDGET, min(MAX_SPATIAL_BUDGET, value))


def _tile_energy(pixels: list[int], width: int, height: int, col: int, row: int, cols: int, rows: int) -> float:
    x0 = int(col * width / cols)
    x1 = int((col + 1) * width / cols)
    y0 = int(row * height / rows)
    y1 = int((row + 1) * height / rows)
    if x1 <= x0 or y1 <= y0:
        return 0.0
    vals: list[int] = []
    for y in range(y0, y1):
        base = y * width
        vals.extend(pixels[base + x0 : base + x1])
    if len(vals) < 2:
        return 0.0
    mean = sum(vals) / len(vals)
    var = sum((p - mean) ** 2 for p in vals) / len(vals)
    return float(var)


def analyze_keyframe_spatial(path: str | Path, *, grid: int = GRID) -> dict:
    """Edge-energy tile map → subject dominance + soft focus hint.

    Returns zeros / center focus when the keyframe is missing or unreadable.
    """
    empty = {
        "focus_x": DEFAULT_FOCUS,
        "focus_y": DEFAULT_FOCUS,
        "dominance": 0.0,
        "concentration": 0.0,
        "entropy": 0.0,
        "busy": False,
        "ambiguous": False,
        "peak_tile": [grid // 2, grid // 2],
        "tile_energies": [],
        "reason": "unreadable keyframe",
        "ok": False,
    }
    try:
        from PIL import Image, ImageFilter
    except ImportError:
        return empty
    file_path = Path(path)
    if not file_path.exists() or file_path.stat().st_size < 32:
        return empty
    try:
        image = Image.open(file_path).convert("L")
        edges = image.filter(ImageFilter.FIND_EDGES)
        width, height = edges.size
        if width < grid or height < grid:
            return empty
        pixels = list(edges.getdata())
    except Exception:
        return empty

    cols = rows = max(2, int(grid))
    energies: list[list[float]] = []
    flat: list[float] = []
    for row in range(rows):
        row_vals: list[float] = []
        for col in range(cols):
            energy = _tile_energy(pixels, width, height, col, row, cols, rows)
            row_vals.append(energy)
            flat.append(energy)
        energies.append(row_vals)

    total = sum(flat) + 1e-9
    peak = max(flat) if flat else 0.0
    peak_share = peak / total
    mean = total / max(1, len(flat))
    peak_over_mean = peak / (mean + 1e-9)
    # Herfindahl concentration in [1/n, 1]; higher = more subject-dominant.
    probs = [e / total for e in flat]
    concentration = sum(p * p for p in probs)
    entropy = 0.0
    log_n = math.log(len(flat)) if len(flat) > 1 else 1.0
    for p in probs:
        if p > 0:
            entropy -= p * math.log(p)
    entropy_norm = min(1.0, entropy / log_n) if log_n > 0 else 0.0
    # Dominance blends peak share with concentration so a single sharp tile wins.
    dominance = max(peak_share, concentration)

    peak_i = flat.index(peak) if flat else 0
    peak_row = peak_i // cols
    peak_col = peak_i % cols
    focus_x = round((peak_col + 0.5) / cols, 4)
    focus_y = round((peak_row + 0.5) / rows, 4)
    busy = entropy_norm >= ENTROPY_AMBIGUOUS_MIN
    # Ambiguous: energy is spread (low concentration) and frame looks busy.
    ambiguous = concentration <= DOMINANCE_AMBIGUOUS_MAX and busy
    reason_bits = [
        f"dominance={dominance:.3f}",
        f"concentration={concentration:.3f}",
        f"entropy={entropy_norm:.3f}",
        f"peak_tile={peak_col},{peak_row}",
        f"peak_over_mean={peak_over_mean:.2f}",
    ]
    if ambiguous:
        reason_bits.append("busy/low-dominance")
    elif concentration > DOMINANCE_AMBIGUOUS_MAX:
        reason_bits.append("subject-dominant")
    else:
        reason_bits.append("low-dominance")

    return {
        "focus_x": focus_x,
        "focus_y": focus_y,
        "dominance": round(dominance, 4),
        "concentration": round(concentration, 4),
        "entropy": round(entropy_norm, 4),
        "busy": busy,
        "ambiguous": ambiguous,
        "peak_tile": [peak_col, peak_row],
        "tile_energies": [[round(v, 2) for v in row] for row in energies],
        "reason": "; ".join(reason_bits),
        "ok": True,
    }


def focus_hint_from_analysis(analysis: dict, *, confidence_scale: float = 1.0) -> dict:
    """Soft cover-crop suggestion. Confidence rises when dominance is clear."""
    dominance = float(analysis.get("dominance") or 0.0)
    ambiguous = bool(analysis.get("ambiguous"))
    # Ambiguous frames still get a peak hint, but lower confidence.
    if ambiguous:
        confidence = round(max(0.15, min(0.55, 0.2 + dominance * confidence_scale)), 4)
    else:
        confidence = round(max(0.2, min(0.95, 0.35 + dominance * 1.4 * confidence_scale)), 4)
    return {
        "focus_x": float(analysis.get("focus_x", DEFAULT_FOCUS)),
        "focus_y": float(analysis.get("focus_y", DEFAULT_FOCUS)),
        "confidence": confidence,
        "dominance": round(dominance, 4),
        "entropy": float(analysis.get("entropy") or 0.0),
        "ambiguous": ambiguous,
        "reason": str(analysis.get("reason") or "spatial tile peak"),
    }


def is_high_value_span(card: dict, peers: list[dict] | None = None) -> bool:
    """High-value: absolute score floor or top fraction among peers."""
    try:
        score = float(card.get("score") or 0.0)
    except (TypeError, ValueError):
        return False
    if score >= HIGH_VALUE_SCORE_FLOOR:
        return True
    if not peers:
        return False
    scores = sorted((float(c.get("score") or 0.0) for c in peers), reverse=True)
    if not scores:
        return False
    cutoff_idx = max(0, int(math.ceil(len(scores) * HIGH_VALUE_TOP_FRAC)) - 1)
    return score + 1e-9 >= scores[cutoff_idx]


def is_spatially_ambiguous(analysis: dict) -> bool:
    return bool(analysis.get("ok")) and bool(analysis.get("ambiguous"))


def annotate_span_spatial(card: dict, keyframe_path: str | Path | None = None) -> dict:
    """Attach ``spatial_ambiguous`` + ``focus_hint`` without mutating role fields."""
    path = keyframe_path or card.get("keyframe_path") or card.get("keyframe") or ""
    analysis = analyze_keyframe_spatial(path)
    hint = focus_hint_from_analysis(analysis)
    out = dict(card)
    out["spatial_ambiguous"] = is_spatially_ambiguous(analysis)
    out["focus_hint"] = hint
    out["spatial_reason"] = analysis.get("reason")
    return out


def select_spatial_targets(cards: list[dict]) -> list[dict]:
    """High-value spans whose keyframe reads as busy / low-dominance."""
    if not cards:
        return []
    targets: list[dict] = []
    for card in cards:
        if not is_high_value_span(card, cards):
            continue
        annotated = annotate_span_spatial(card)
        if annotated.get("spatial_ambiguous"):
            targets.append(annotated)
    targets.sort(key=lambda c: (-float(c.get("score") or 0.0), float(c.get("in_s") or 0.0)))
    return targets


def spatial_windows(in_s: float, out_s: float, budget: int) -> list[tuple[float, float]]:
    """Reuse temporal refine windows for spatial densify samples."""
    return refine_windows(in_s, out_s, budget)


def focus_drift(x: float, y: float, hint: dict | None) -> float:
    if not hint:
        return 0.0
    try:
        hx = float(hint.get("focus_x", DEFAULT_FOCUS))
        hy = float(hint.get("focus_y", DEFAULT_FOCUS))
    except (TypeError, ValueError):
        return 0.0
    return math.hypot(float(x) - hx, float(y) - hy)


def spatial_refocus_warning(
    clip_id: str,
    x: float,
    y: float,
    hint: dict | None,
    *,
    fit: str | None = None,
) -> str | None:
    """Warn-only when cover focus ignores a confident spatial hint."""
    if not hint:
        return None
    framing = (fit or "cover").strip().lower()
    if framing in {"fit", "fit_pad", "fit_blur", "letterbox"}:
        return None
    try:
        confidence = float(hint.get("confidence") or 0.0)
        hx = float(hint.get("focus_x", DEFAULT_FOCUS))
        hy = float(hint.get("focus_y", DEFAULT_FOCUS))
    except (TypeError, ValueError):
        return None
    if confidence < 0.25:
        return None
    drift = focus_drift(x, y, hint)
    centered = abs(x - DEFAULT_FOCUS) < 0.02 and abs(y - DEFAULT_FOCUS) < 0.02
    if drift < FOCUS_DRIFT_WARN and not (centered and drift >= 0.05):
        return None
    return (
        f"SPEC-ANA-15: clip {clip_id} cover focus ({x:.2f},{y:.2f}) differs from "
        f"spatial hint ({hx:.2f},{hy:.2f}); soft suggestion only"
    )


def spatial_cover_warnings(
    clips: list,
    hints_by_clip: dict[str, dict],
) -> list[str]:
    """Review/export soft warnings for cover clips that keep default center."""
    warns: list[str] = []
    for clip in clips:
        hint = hints_by_clip.get(clip.id)
        if not hint:
            continue
        framing = getattr(clip, "fit", None) or "cover"
        msg = spatial_refocus_warning(
            clip.id,
            float(getattr(clip, "focus_x", DEFAULT_FOCUS)),
            float(getattr(clip, "focus_y", DEFAULT_FOCUS)),
            hint,
            fit=framing,
        )
        if msg:
            warns.append(msg)
    return warns


def pick_hint_for_span(
    spatial_payload: dict | None,
    *,
    media_id: str,
    in_s: float,
    out_s: float,
) -> dict | None:
    """Best focus hint overlapping a clip's source span from understand cache."""
    if not spatial_payload:
        return None
    spans = spatial_payload.get("spans") or []
    mid = (float(in_s) + float(out_s)) / 2.0
    overlapping: list[dict] = []
    for span in spans:
        if str(span.get("media_id") or "") != media_id:
            continue
        try:
            a = float(span.get("in_s", 0.0))
            b = float(span.get("out_s", 0.0))
        except (TypeError, ValueError):
            continue
        if a - 1e-6 <= mid <= b + 1e-6 or (a <= float(in_s) and b >= float(out_s)):
            hint = span.get("focus_hint")
            if isinstance(hint, dict):
                overlapping.append({**span, "_hint": hint})
    if not overlapping:
        # Fall back to any media-level hint.
        for span in spans:
            if str(span.get("media_id") or "") != media_id:
                continue
            hint = span.get("focus_hint")
            if isinstance(hint, dict):
                overlapping.append({**span, "_hint": hint})
                break
    if not overlapping:
        return None
    best = max(
        overlapping,
        key=lambda s: (
            float((s.get("_hint") or {}).get("confidence") or 0.0),
            float(s.get("score") or 0.0),
        ),
    )
    return best.get("_hint")


__all__ = [
    "DEFAULT_SPATIAL_BUDGET",
    "DOMINANCE_AMBIGUOUS_MAX",
    "ENTROPY_AMBIGUOUS_MIN",
    "FOCUS_DRIFT_WARN",
    "GRID",
    "HIGH_VALUE_SCORE_FLOOR",
    "MAX_SPATIAL_BUDGET",
    "MIN_SPATIAL_BUDGET",
    "analyze_keyframe_spatial",
    "annotate_span_spatial",
    "clamp_spatial_budget",
    "focus_drift",
    "focus_hint_from_analysis",
    "is_high_value_span",
    "is_spatially_ambiguous",
    "pick_hint_for_span",
    "select_spatial_targets",
    "spatial_cover_warnings",
    "spatial_refocus_warning",
    "spatial_windows",
]
