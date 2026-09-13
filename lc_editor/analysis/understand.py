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
"""

from __future__ import annotations

import json
import os
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


def best_role_hint(
    shot: Shot,
    roles: list[str],
    *,
    first_media_id: str | None = None,
    sizes: dict[str, tuple[int, int]] | None = None,
) -> tuple[str, float]:
    best_role = roles[0] if roles else "detail"
    best_score = float("-inf")
    for role in roles:
        score = score_role_for_shot(shot, role, first_media_id=first_media_id, sizes=sizes)
        if score > best_score or (score == best_score and role < best_role):
            best_score = score
            best_role = role
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
) -> dict:
    scores = role_scores_for_shot(shot, roles, first_media_id=first_media_id, sizes=sizes)
    role, score = best_role_hint(shot, roles, first_media_id=first_media_id, sizes=sizes)
    return {
        "media_id": shot.media_id,
        "in_s": round(float(shot.in_s), 4),
        "out_s": round(float(shot.out_s), 4),
        "role_hint": role,
        "score": round(float(score), 4),
        "keyframe_path": shot.keyframe,
        "reason": reason_for(shot, role, score, role_scores=scores),
        "role_scores": scores,
        "shot_id": shot.id,
    }


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
    return {
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
    "apply_understand_tags",
    "best_role_hint",
    "build_understand_timeline",
    "card_from_shot",
    "cards_from_tagged_shots",
    "candidate_priority",
    "clamp_budget",
    "coverage_indices",
    "load_understand_cache",
    "parent_shot_for_span",
    "refine_windows",
    "resolve_understand_roles",
    "role_scores_for_shot",
    "score_role_for_shot",
    "select_candidate_shots",
    "shot_has_any_understand_tag",
    "shot_has_understand_role",
    "understand_boost",
    "understand_path",
    "understand_tag",
    "write_understand_cache",
]
