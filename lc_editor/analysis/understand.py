"""Hierarchical cheap media understanding (Train A + B selection + Train C roles).

Reuses the import shot index. Scores only candidate spans (keyframes already
on disk). No full-video VLM. No large weights required.

Train B swaps the default candidate picker for FOCUS/AKS-inspired adaptive
selection (see ``lc_editor.analysis.adaptive``) while keeping Train A card
shapes and refine APIs stable.

Train C maps spans onto PROCESS_ROLES with clear per-role scores/reasons and
builds Director story cards via ``build_understand_timeline``.

Train D (LENS-lite) lives in ``lc_editor.analysis.spatial``: spatial densify
and soft ``focus_x``/``focus_y`` hints for busy high-value spans.

Train F retunes PROCESS_ROLES scoring / mapping so silent detailing albums
surface before/after/interior/wheel (not wash/skip_face monopolies) and
feeds denser role hints into highlights packing.

Train G adds soft priors (filename tokens, album order, temporal thirds) and
an album diversify pass so wash/skip_face cannot monopolize silent detailing
when visual cues are weak. Falls back to ``media_tag`` priors when tags exist.
"""

from __future__ import annotations

import json
import os
import re
from pathlib import Path

from lc_editor.analysis.manifest import Shot
from lc_editor.analysis.rank import (
    PROCESS_ROLES,
    PROCESS_STORY_ORDER,
    UNDERSTAND_TAG_PREFIX,
    score_shot,
    shot_has_any_understand_tag,
    shot_has_understand_role,
    understand_boost,
    understand_tags_for_role,
)
from lc_editor.models import SHOT_MAX_S

DEFAULT_BUDGET_FRAMES = 48
MIN_BUDGET_FRAMES = 8
MAX_BUDGET_FRAMES = 64
DEFAULT_REFINE_BUDGET = 16

# Default process / album roles for Director feed (Train C PROCESS_ROLES set).
DEFAULT_PROCESS_ROLES = (
    "before",
    "wash",
    "wheel",
    "interior",
    "engine",
    "machine",
    "after",
    "hero",
    "skip_face",
)

# Understand-only aliases that map onto process scorers.
UNDERSTAND_SCORE_ALIAS = {
    "polish": "after",
    "detail": "detail",
}

QUERY_PROCESS = frozenset({"", "process", "album", "detailing", "default"})

ROLE_REASON_HINTS = {
    "before": "dusty/dull still",
    "wash": "wet-work motion",
    "wheel": "sharp wheel detail",
    "interior": "cabin still detail",
    "engine": "engine motion/audio",
    "machine": "tool/polisher work",
    "after": "clean/shiny payoff",
    "polish": "clean/shiny payoff",
    "hero": "hero still",
    "skip_face": "calm wide / skip face",
    "detail": "sharp still detail",
}

# Soft prior when media_tag(role=…) matches a process role (Train F/G).
MEDIA_ROLE_PRIOR = 0.32
FILENAME_ROLE_PRIOR = 0.16
ORDER_ROLE_PRIOR = 0.12
TEMPORAL_ROLE_PRIOR = 0.12
# Prefer story labels over monopoly roles when scores are within this margin.
ROLE_MARGIN_PREFER = 0.06
# Wider margin when a soft prior agrees with the story role (Train G).
ROLE_MARGIN_PRIOR = 0.16
# media_tag is an agent hint: prefer it when still competitive after prior.
MEDIA_TAG_MARGIN = 0.2
MONOPOLY_ROLES = frozenset({"wash", "skip_face", "hero"})
# Close-score story roles that should beat wash/skip_face/hero monopolies.
# Exclude machine/engine: they compete on motion and must win on their own score.
STORY_DETAIL_ROLES = frozenset({"before", "after", "interior", "wheel"})
PROCESS_WORK_ROLES = frozenset({"wash", "machine"})
DETAIL_STILL_ROLES = frozenset({"interior", "wheel"})

# Filename / path tokens → process role (word-boundary match, Train G).
FILENAME_ROLE_TOKENS: dict[str, tuple[str, ...]] = {
    "before": ("before", "prewash", "pre_wash", "dirty", "dusty", "arrival", "intake"),
    "after": ("after", "done", "final", "reveal", "glossy", "shiny", "payoff", "finished"),
    "wash": ("wash", "foam", "soap", "rinse", "wetwork", "wet_work", "suds"),
    "interior": ("interior", "cabin", "dash", "seat", "inside", "cockpit"),
    "wheel": ("wheel", "rim", "tire", "tyre", "alloy"),
    "engine": ("engine", "motor", "bay"),
    "machine": ("machine", "buffer", "polisher", "rotary", "tooling"),
    "hero": ("hero", "beauty", "glamour"),
    "detail": ("detail", "closeup", "close_up"),
}


def clamp_budget(budget_frames: int | None, default: int = DEFAULT_BUDGET_FRAMES) -> int:
    if budget_frames is None:
        return default
    try:
        value = int(budget_frames)
    except (TypeError, ValueError):
        return default
    return max(MIN_BUDGET_FRAMES, min(MAX_BUDGET_FRAMES, value))


def understand_tag(role: str) -> str:
    return f"{UNDERSTAND_TAG_PREFIX}{role}"


def tags_for_role(role: str) -> list[str]:
    """Tags that mean this role for preference / search."""
    return understand_tags_for_role(role)


def resolve_understand_roles(
    query: str | None = None,
    roles: list[str] | None = None,
) -> list[str]:
    if roles:
        out: list[str] = []
        for role in roles:
            name = str(role).strip().lower()
            if name and name not in out:
                out.append(name)
        return out or list(DEFAULT_PROCESS_ROLES)
    text = (query or "process").strip().lower()
    if text in QUERY_PROCESS:
        return list(DEFAULT_PROCESS_ROLES)
    if "," in text or " " in text:
        parts = [p.strip().lower() for p in text.replace(",", " ").split() if p.strip()]
        known = [
            p
            for p in parts
            if p in DEFAULT_PROCESS_ROLES or p in PROCESS_ROLES or p in UNDERSTAND_SCORE_ALIAS
        ]
        if known:
            return known
    if text in DEFAULT_PROCESS_ROLES or text in PROCESS_ROLES or text in UNDERSTAND_SCORE_ALIAS:
        return [text]
    return list(DEFAULT_PROCESS_ROLES)


def score_role_for_shot(
    shot: Shot,
    role: str,
    *,
    first_media_id: str | None = None,
    sizes: dict[str, tuple[int, int]] | None = None,
) -> float:
    mapped = UNDERSTAND_SCORE_ALIAS.get(role, role)
    try:
        return score_shot(shot, mapped, first_media_id=first_media_id, sizes=sizes)
    except ValueError:
        # Unknown understand role: fall back to site_detail heuristic.
        return score_shot(shot, "site_detail", first_media_id=first_media_id, sizes=sizes)


def role_scores_for_shot(
    shot: Shot,
    roles: list[str],
    *,
    first_media_id: str | None = None,
    sizes: dict[str, tuple[int, int]] | None = None,
) -> dict[str, float]:
    return {
        role: round(
            float(score_role_for_shot(shot, role, first_media_id=first_media_id, sizes=sizes)),
            4,
        )
        for role in roles
    }


def _normalize_media_role(media_role: str | None) -> str | None:
    if not media_role:
        return None
    text = str(media_role).strip().lower()
    if text == "polish":
        return "after"
    return text or None


def filename_role_priors(source_path: str | None) -> dict[str, float]:
    """Soft boosts from filename / path tokens (Train G)."""
    if not source_path:
        return {}
    text = str(source_path).replace("\\", "/").lower()
    stem = Path(text).stem
    blob = f"{stem} {text}"
    out: dict[str, float] = {}
    for role, tokens in FILENAME_ROLE_TOKENS.items():
        for token in tokens:
            if re.search(rf"(?<![a-z0-9]){re.escape(token)}(?![a-z0-9])", blob):
                out[role] = max(out.get(role, 0.0), FILENAME_ROLE_PRIOR)
                break
    return out


def album_order_priors(media_index: int | None, media_count: int | None) -> dict[str, float]:
    """Early album clips → before; late clips → after (Train G)."""
    if media_index is None or media_count is None or media_count <= 1:
        return {}
    frac = float(media_index) / float(max(1, media_count - 1))
    out: dict[str, float] = {}
    if frac <= 0.25:
        out["before"] = ORDER_ROLE_PRIOR
    elif frac >= 0.75:
        out["after"] = ORDER_ROLE_PRIOR
    elif 0.35 <= frac <= 0.65:
        out["wash"] = ORDER_ROLE_PRIOR * 0.35
        out["machine"] = ORDER_ROLE_PRIOR * 0.35
        out["interior"] = ORDER_ROLE_PRIOR * 0.25
        out["wheel"] = ORDER_ROLE_PRIOR * 0.25
    return out


def temporal_third_priors(
    shot: Shot,
    *,
    media_duration_s: float | None = None,
) -> dict[str, float]:
    """First third → before, mid → process, last third → after (Train G).

    Only applies when media duration is known. Short indexed shots must not
    invent a local third from their own tiny window.
    """
    if media_duration_s is None:
        return {}
    duration = float(media_duration_s)
    if duration <= 1e-6:
        return {}
    mid = (float(shot.in_s) + float(shot.out_s)) / 2.0
    frac = max(0.0, min(1.0, mid / duration))
    out: dict[str, float] = {}
    if frac < 1.0 / 3.0:
        out["before"] = TEMPORAL_ROLE_PRIOR
        out["after"] = -TEMPORAL_ROLE_PRIOR * 0.5
    elif frac > 2.0 / 3.0:
        out["after"] = TEMPORAL_ROLE_PRIOR
        out["before"] = -TEMPORAL_ROLE_PRIOR * 0.5
    else:
        out["wash"] = TEMPORAL_ROLE_PRIOR * 0.3
        out["machine"] = TEMPORAL_ROLE_PRIOR * 0.3
        out["interior"] = TEMPORAL_ROLE_PRIOR * 0.35
        out["wheel"] = TEMPORAL_ROLE_PRIOR * 0.35
        out["skip_face"] = -TEMPORAL_ROLE_PRIOR * 0.4
    return out


def soft_role_priors(
    shot: Shot,
    *,
    media_role: str | None = None,
    source_path: str | None = None,
    media_index: int | None = None,
    media_count: int | None = None,
    media_duration_s: float | None = None,
) -> dict[str, float]:
    """Combine media_tag + filename + album order + temporal thirds."""
    merged: dict[str, float] = {}

    def add(priors: dict[str, float]) -> None:
        for role, boost in priors.items():
            merged[role] = merged.get(role, 0.0) + float(boost)

    prior = _normalize_media_role(media_role)
    if prior:
        add({prior: MEDIA_ROLE_PRIOR})
    add(filename_role_priors(source_path))
    add(album_order_priors(media_index, media_count))
    add(temporal_third_priors(shot, media_duration_s=media_duration_s))
    return merged


def best_role_hint(
    shot: Shot,
    roles: list[str],
    *,
    first_media_id: str | None = None,
    sizes: dict[str, tuple[int, int]] | None = None,
    media_role: str | None = None,
    source_path: str | None = None,
    media_index: int | None = None,
    media_count: int | None = None,
    media_duration_s: float | None = None,
) -> tuple[str, float]:
    """Pick the best process role for a span (Train F/G anti-monopoly mapping)."""
    if not roles:
        return "detail", 0.0
    adjusted: dict[str, float] = {}
    for role in roles:
        adjusted[role] = float(
            score_role_for_shot(shot, role, first_media_id=first_media_id, sizes=sizes)
        )
    priors = soft_role_priors(
        shot,
        media_role=media_role,
        source_path=source_path,
        media_index=media_index,
        media_count=media_count,
        media_duration_s=media_duration_s,
    )
    for role, boost in priors.items():
        if role in adjusted:
            adjusted[role] = adjusted[role] + boost

    ranked = sorted(adjusted.items(), key=lambda kv: (-kv[1], kv[0]))
    best_role, best_score = ranked[0]
    prior = _normalize_media_role(media_role)
    # Explicit media_tag: prefer tagged role when it remains competitive.
    if prior and prior in adjusted and best_role != prior:
        tagged_score = adjusted[prior]
        if best_score - tagged_score <= MEDIA_TAG_MARGIN:
            best_role, best_score = prior, tagged_score
    # When wash/skip_face/hero barely win, prefer a story role with close score.
    if best_role in MONOPOLY_ROLES and len(ranked) > 1:
        for role, score in ranked[1:]:
            if role not in STORY_DETAIL_ROLES:
                continue
            margin = ROLE_MARGIN_PRIOR if priors.get(role, 0.0) > 0 else ROLE_MARGIN_PREFER
            if best_score - score <= margin:
                best_role, best_score = role, score
            break
    return best_role, best_score

def reason_for(
    shot: Shot,
    role: str,
    score: float,
    *,
    role_scores: dict[str, float] | None = None,
) -> str:
    m = shot.metrics
    bits = [
        f"role={role}",
        f"motion={m.motion:.2f}",
        f"sharp={m.sharpness:.2f}",
        f"blur={m.blur:.2f}",
        f"luma={m.luma_mean:.2f}",
        f"audio={m.audio_class}",
        f"score={score:.3f}",
    ]
    hint = ROLE_REASON_HINTS.get(role)
    if hint:
        bits.append(hint)
    if role in ("wash", "machine", "engine", "journey") and m.motion >= 0.35:
        bits.append("high-motion candidate")
    if role in ("wheel", "interior", "detail", "polish", "after", "before", "hero") and m.sharpness >= 0.45:
        bits.append("sharp still detail")
    if role in ("after", "polish", "hero") and m.luma_mean >= 0.55:
        bits.append("bright payoff")
    if role == "before" and m.luma_mean <= 0.45:
        bits.append("low-luma dusty")
    if m.audio_class == "engine" and role in ("engine", "machine", "wash"):
        bits.append("engine audio")
    if role_scores and len(role_scores) > 1:
        ranked = sorted(role_scores.items(), key=lambda kv: (-kv[1], kv[0]))
        runner = next((name for name, _ in ranked if name != role), None)
        if runner is not None:
            margin = role_scores[role] - role_scores[runner]
            bits.append(f"margin_vs_{runner}={margin:.3f}")
    return "; ".join(bits)


def candidate_priority(shot: Shot) -> float:
    """Cheap interestingness for picking which indexed shots to score."""
    m = shot.metrics
    audio_peak = 0.0
    if m.audio_class == "engine":
        audio_peak = 0.35
    elif m.audio_class == "speech":
        audio_peak = 0.25
    elif m.audio_class == "ambient":
        audio_peak = 0.1
    rms_boost = 0.0
    if m.audio_rms_db is not None and m.audio_rms_db > -25:
        rms_boost = min(0.2, (m.audio_rms_db + 40) / 100.0)
    return (
        0.45 * m.motion
        + 0.25 * m.sharpness
        + 0.15 * (1.0 - m.blur)
        + audio_peak
        + rms_boost
        + 0.05 * m.luma_spread
    )


def coverage_indices(n: int, slots: int) -> list[int]:
    if n <= 0 or slots <= 0:
        return []
    if slots >= n:
        return list(range(n))
    if slots == 1:
        return [n // 2]
    out: list[int] = []
    for i in range(slots):
        idx = int(round(i * (n - 1) / (slots - 1)))
        if idx not in out:
            out.append(idx)
    return out


def select_candidate_shots(shots: list[Shot], budget: int) -> list[Shot]:
    """Pick up to ``budget`` indexed shots: motion / audio peaks + coverage grid."""
    if not shots:
        return []
    if len(shots) <= budget:
        return list(shots)

    ordered = sorted(shots, key=lambda s: (s.in_s, s.id))
    picked: dict[str, Shot] = {}

    # Coverage grid first so long clips always get evenly spaced samples.
    cover_slots = max(2, budget // 3)
    for idx in coverage_indices(len(ordered), cover_slots):
        shot = ordered[idx]
        picked[shot.id] = shot

    # High motion / audio peaks fill the rest.
    remaining = budget - len(picked)
    if remaining > 0:
        ranked = sorted(ordered, key=lambda s: (-candidate_priority(s), s.id))
        for shot in ranked:
            if shot.id in picked:
                continue
            picked[shot.id] = shot
            remaining -= 1
            if remaining <= 0:
                break

    # Cut-boundary preference: ensure first and last shot when budget allows.
    if ordered[0].id not in picked and len(picked) < budget:
        picked[ordered[0].id] = ordered[0]
    if ordered[-1].id not in picked and len(picked) < budget:
        if len(picked) >= budget:
            weakest = min(picked.values(), key=lambda s: (candidate_priority(s), s.id))
            if weakest.id not in (ordered[0].id, ordered[-1].id):
                del picked[weakest.id]
                picked[ordered[-1].id] = ordered[-1]
        else:
            picked[ordered[-1].id] = ordered[-1]

    return sorted(picked.values(), key=lambda s: (s.in_s, s.id))


def card_from_shot(
    shot: Shot,
    roles: list[str],
    *,
    first_media_id: str | None = None,
    sizes: dict[str, tuple[int, int]] | None = None,
    media_role: str | None = None,
    source_path: str | None = None,
    media_index: int | None = None,
    media_count: int | None = None,
    media_duration_s: float | None = None,
) -> dict:
    scores = role_scores_for_shot(shot, roles, first_media_id=first_media_id, sizes=sizes)
    role, score = best_role_hint(
        shot,
        roles,
        first_media_id=first_media_id,
        sizes=sizes,
        media_role=media_role,
        source_path=source_path,
        media_index=media_index,
        media_count=media_count,
        media_duration_s=media_duration_s,
    )
    margin = None
    if scores and len(scores) > 1:
        ranked = sorted(scores.items(), key=lambda kv: (-kv[1], kv[0]))
        runner = next((name for name, _ in ranked if name != role), None)
        if runner is not None:
            margin = scores[role] - scores[runner]
    priors = soft_role_priors(
        shot,
        media_role=media_role,
        source_path=source_path,
        media_index=media_index,
        media_count=media_count,
        media_duration_s=media_duration_s,
    )
    reason = reason_for(shot, role, score, role_scores=scores)
    if priors.get(role, 0.0) > 0:
        reason = f"{reason}; soft_prior={role}:{priors[role]:.2f}"
    return {
        "media_id": shot.media_id,
        "in_s": round(float(shot.in_s), 4),
        "out_s": round(float(shot.out_s), 4),
        "role_hint": role,
        "score": round(float(score), 4),
        "keyframe_path": shot.keyframe,
        "reason": reason,
        "role_scores": scores,
        "shot_id": shot.id,
        "media_role": _normalize_media_role(media_role),
        "needs_confirmation": bool(margin is not None and margin <= ROLE_MARGIN_PREFER),
        "media_index": media_index,
        "source_path": source_path,
    }


def _role_of(card: dict) -> str:
    role = str(card.get("role_hint") or card.get("role") or "").strip().lower()
    if role == "polish":
        return "after"
    return role


def _card_album_key(card: dict) -> tuple:
    idx = card.get("media_index")
    try:
        order = int(idx) if idx is not None else 10_000
    except (TypeError, ValueError):
        order = 10_000
    return (order, float(card.get("in_s") or 0.0), str(card.get("media_id") or ""))


def _score_for_role(card: dict, role: str) -> float:
    scores = card.get("role_scores") or {}
    if isinstance(scores, dict) and role in scores:
        try:
            return float(scores[role])
        except (TypeError, ValueError):
            pass
    try:
        return float(card.get("score") or 0.0)
    except (TypeError, ValueError):
        return 0.0


def _promote_card(card: dict, role: str, *, why: str) -> dict:
    updated = dict(card)
    updated["role_hint"] = role
    reason = str(card.get("reason") or "")
    note = f"diversify:{why}→{role}"
    updated["reason"] = f"{reason}; {note}" if reason else note
    # Keep score competitive so packing still prefers these bookends.
    base = _score_for_role(card, role)
    try:
        cur = float(card.get("score") or 0.0)
    except (TypeError, ValueError):
        cur = 0.0
    updated["score"] = round(max(cur, base + 0.05), 4)
    return updated


def diversify_process_album(cards: list[dict]) -> list[dict]:
    """Ensure album histogram covers before / wash|machine / interior|wheel / after.

    When visual cues collapse to wash/skip_face/engine/machine, promote the best
    soft-prior candidates. If a class is still impossible (empty album), leave as-is;
    agents can still recover via ``media_tag`` priors on a re-run.
    """
    if not cards:
        return []
    out = [dict(c) for c in cards]
    targets: list[tuple[str, frozenset[str]]] = [
        ("before", frozenset({"before"})),
        ("wash", PROCESS_WORK_ROLES),
        ("interior", DETAIL_STILL_ROLES),
        ("after", frozenset({"after"})),
    ]
    reserved: set[int] = set()

    def present_roles() -> set[str]:
        return {_role_of(c) for c in out}

    for preferred, acceptable in targets:
        if present_roles() & acceptable:
            continue
        pool = [(i, c) for i, c in enumerate(out) if i not in reserved]
        if not pool:
            continue
        pick_role = preferred
        if preferred == "before":
            pool.sort(key=lambda ic: (_card_album_key(ic[1]), -_score_for_role(ic[1], "before")))
            pick_role = "before"
            why = "early_bookend"
        elif preferred == "after":
            pool.sort(key=lambda ic: (_card_album_key(ic[1]), _score_for_role(ic[1], "after")))
            pool.reverse()
            pick_role = "after"
            why = "late_bookend"
        elif preferred == "interior":
            pool.sort(
                key=lambda ic: (
                    -max(_score_for_role(ic[1], "interior"), _score_for_role(ic[1], "wheel")),
                    _card_album_key(ic[1]),
                )
            )
            best = pool[0][1]
            pick_role = (
                "wheel"
                if _score_for_role(best, "wheel") > _score_for_role(best, "interior")
                else "interior"
            )
            why = "detail_still"
        else:
            pool.sort(
                key=lambda ic: (
                    -max(_score_for_role(ic[1], "wash"), _score_for_role(ic[1], "machine")),
                    _card_album_key(ic[1]),
                )
            )
            best = pool[0][1]
            pick_role = (
                "machine"
                if _score_for_role(best, "machine") > _score_for_role(best, "wash")
                else "wash"
            )
            why = "process_work"
        idx = pool[0][0]
        out[idx] = _promote_card(out[idx], pick_role, why=why)
        reserved.add(idx)

    return out


def apply_understand_tags(shots: list[Shot], cards: list[dict]) -> list[Shot]:
    """Stamp understand:{role} onto matching shots; drop stale understand tags."""
    by_id = {card["shot_id"]: card for card in cards if card.get("shot_id")}
    updated: list[Shot] = []
    for shot in shots:
        tags = [t for t in (shot.tags or []) if not str(t).startswith(UNDERSTAND_TAG_PREFIX)]
        card = by_id.get(shot.id)
        if card:
            tag = understand_tag(str(card["role_hint"]))
            if tag not in tags:
                tags.append(tag)
        updated.append(shot.model_copy(update={"tags": tags}))
    return updated


def understand_path(analysis_dir: Path, proxy_hash: str) -> Path:
    return analysis_dir / f"{proxy_hash}.understand.json"


def write_understand_cache(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    try:
        tmp.write_text(text, encoding="utf-8")
        os.replace(tmp, path)
    except Exception:
        if tmp.exists():
            tmp.unlink(missing_ok=True)
        raise


def load_understand_cache(path: Path) -> dict | None:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def refine_windows(in_s: float, out_s: float, budget: int) -> list[tuple[float, float]]:
    """Dense equal windows inside [in_s, out_s] (at most budget)."""
    start = round(float(in_s), 4)
    end = round(float(out_s), 4)
    if end <= start:
        return []
    length = end - start
    n = max(2, min(budget, max(2, int(round(length / max(0.4, SHOT_MAX_S / 4))))))
    n = min(n, budget)
    step = length / n
    windows: list[tuple[float, float]] = []
    for i in range(n):
        a = start + i * step
        b = end if i == n - 1 else start + (i + 1) * step
        if b - a >= 0.2:
            windows.append((round(a, 4), round(b, 4)))
    return windows or [(start, end)]


def parent_shot_for_span(shots: list[Shot], in_s: float, out_s: float) -> Shot | None:
    mid = (in_s + out_s) / 2.0
    overlapping = [s for s in shots if s.in_s - 1e-6 <= mid < s.out_s + 1e-6]
    if overlapping:
        return min(overlapping, key=lambda s: (s.duration_s, s.id))
    if not shots:
        return None
    return min(shots, key=lambda s: (abs((s.in_s + s.out_s) / 2 - mid), s.id))


def _beat_from_card(
    card: dict,
    *,
    shoot_day: int | str | None = None,
    media_role: str | None = None,
    source: str = "understand",
) -> dict:
    role = str(card.get("role_hint") or card.get("role") or "detail")
    beat = {
        "role": role,
        "media_id": card.get("media_id"),
        "in_s": round(float(card.get("in_s", 0.0)), 4),
        "out_s": round(float(card.get("out_s", 0.0)), 4),
        "score": round(float(card.get("score", 0.0)), 4),
        "keyframe_path": card.get("keyframe_path") or card.get("keyframe") or "",
        "reason": card.get("reason") or f"role={role}",
        "role_scores": card.get("role_scores") or {},
        "shoot_day": shoot_day,
        "media_role": media_role,
        "source": source,
    }
    if card.get("needs_confirmation"):
        beat["needs_confirmation"] = True
    return beat


def _story_rank(role: str) -> int:
    role = (role or "").strip().lower()
    if role == "polish":
        role = "after"
    try:
        return PROCESS_STORY_ORDER.index(role)
    except ValueError:
        return len(PROCESS_STORY_ORDER)


def build_understand_timeline(
    cards: list[dict],
    *,
    media_meta: dict[str, dict] | None = None,
    top_per_role: int = 2,
    roles: list[str] | None = None,
) -> dict:
    """Structured Director story cards: role-labeled beats in process order."""
    meta = media_meta or {}
    wanted = [r.strip().lower() for r in (roles or list(PROCESS_STORY_ORDER)) if r]
    if not wanted:
        wanted = list(PROCESS_STORY_ORDER)
    by_role: dict[str, list[dict]] = {role: [] for role in wanted}
    for card in cards:
        role = str(card.get("role_hint") or card.get("role") or "").strip().lower()
        if role == "polish":
            role = "after"
        if role not in by_role:
            if roles is not None:
                continue
            by_role[role] = []
        mid = str(card.get("media_id") or "")
        info = meta.get(mid) or {}
        beat = _beat_from_card(
            {**card, "role_hint": role},
            shoot_day=info.get("shoot_day"),
            media_role=info.get("role"),
            source=str(card.get("source") or "understand"),
        )
        by_role.setdefault(role, []).append(beat)

    for role, rows in by_role.items():
        rows.sort(key=lambda b: (-float(b["score"]), str(b.get("media_id") or ""), float(b["in_s"])))
        if top_per_role > 0:
            by_role[role] = rows[:top_per_role]

    ordered_roles = [r for r in PROCESS_STORY_ORDER if r in by_role and by_role[r]]
    for role in sorted(by_role.keys(), key=_story_rank):
        if role not in ordered_roles and by_role[role]:
            ordered_roles.append(role)

    story: list[dict] = []
    for role in ordered_roles:
        story.extend(by_role[role])

    return {
        "beats": story,
        "by_role": {role: by_role[role] for role in ordered_roles},
        "roles_present": ordered_roles,
        "order": list(PROCESS_STORY_ORDER),
        "top_per_role": top_per_role,
    }


def cards_from_tagged_shots(
    shots: list[Shot],
    *,
    media_meta: dict[str, dict] | None = None,
) -> list[dict]:
    """Fallback cards from understand:* shot tags when cache is empty."""
    meta = media_meta or {}
    cards: list[dict] = []
    for shot in shots:
        for tag in shot.tags or []:
            text = str(tag)
            if not text.startswith(UNDERSTAND_TAG_PREFIX):
                continue
            role = text[len(UNDERSTAND_TAG_PREFIX) :].strip().lower()
            if not role:
                continue
            mid = shot.media_id
            info = meta.get(mid) or {}
            score_role = "after" if role == "polish" else role
            try:
                score = float(score_shot(shot, score_role))
            except ValueError:
                score = float(score_shot(shot, "site_detail"))
            cards.append(
                {
                    "media_id": mid,
                    "in_s": round(float(shot.in_s), 4),
                    "out_s": round(float(shot.out_s), 4),
                    "role_hint": role,
                    "score": round(score, 4),
                    "keyframe_path": shot.keyframe,
                    "reason": reason_for(shot, role, score),
                    "role_scores": {},
                    "source": "shot_tag",
                    "shoot_day": info.get("shoot_day"),
                    "media_role": info.get("role"),
                    "captured_at": info.get("captured_at"),
                    "shot_id": shot.id,
                }
            )
    return cards


# Re-export boost / tag helpers for callers that import from understand.
__all__ = [
    "DEFAULT_BUDGET_FRAMES",
    "DEFAULT_PROCESS_ROLES",
    "DEFAULT_REFINE_BUDGET",
    "MAX_BUDGET_FRAMES",
    "MIN_BUDGET_FRAMES",
    "PROCESS_STORY_ORDER",
    "QUERY_PROCESS",
    "album_order_priors",
    "apply_understand_tags",
    "best_role_hint",
    "build_understand_timeline",
    "card_from_shot",
    "cards_from_tagged_shots",
    "candidate_priority",
    "clamp_budget",
    "coverage_indices",
    "diversify_process_album",
    "filename_role_priors",
    "load_understand_cache",
    "parent_shot_for_span",
    "refine_windows",
    "resolve_understand_roles",
    "role_scores_for_shot",
    "score_role_for_shot",
    "select_candidate_shots",
    "shot_has_any_understand_tag",
    "shot_has_understand_role",
    "soft_role_priors",
    "temporal_third_priors",
    "understand_boost",
    "understand_path",
    "understand_tag",
    "write_understand_cache",
]
