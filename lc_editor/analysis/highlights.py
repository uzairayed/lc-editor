"""Train E/F/G: LC-native beat sheet suggestions from understand spans.

``highlights_suggest`` ranks candidate beat sheets for the agent. Prefer
transformation arcs (before → process ASMR → after) over virality or
transcript hacks. Detailing is often silent: do not require speech peaks.
Train F packs enough spans across media toward ``target_s`` (~60s process)
so complete arcs land near 45–70s. Train G promotes soft bookends when
understand collapses to wash/engine/machine so ``arc_complete`` can still
land. Suggest only; never mutate the timeline or auto-export.
"""

from __future__ import annotations

from lc_editor.analysis.provenance import beats_arc_order
from lc_editor.analysis.rank import PROCESS_STORY_ORDER
from lc_editor.analysis.spatial import pick_hint_for_span
from lc_editor.models import (
    DURATION_SOFT_MAX_S,
    MIN_VIDEO_DURATION_S,
    SHOT_ACK_MIN_S,
    SHOT_MAX_S,
)

STYLES = ("process", "reel", "youtube")

BEFORE_ROLES = frozenset({"before"})
PROCESS_ROLES = frozenset(
    {"wash", "engine", "machine", "wheel", "interior", "detail"}
)
AFTER_ROLES = frozenset({"after", "polish"})
HERO_ROLES = frozenset({"hero"})
SKIP_ROLES = frozenset({"skip_face"})

# Narrative fallbacks when style=reel and process roles are sparse.
REEL_HOOK = frozenset({"hook", "before", "hero"})
REEL_JOURNEY = frozenset({"journey", "wash", "engine", "machine"})
REEL_SITE = frozenset({"site_wide", "site_detail", "wheel", "interior", "detail"})
REEL_CLOSER = frozenset({"closer", "after", "polish", "hero"})

DEFAULT_TARGET_PROCESS_S = 60.0
DEFAULT_TARGET_REEL_S = DURATION_SOFT_MAX_S
MIN_TARGET_S = 8.0
MAX_TARGET_S = 180.0
MAX_TARGET_YOUTUBE_S = 43200.0
MAX_CANDIDATES = 3

# Speech / transcript-style peaks are a soft penalty for process arcs
# (detailing ASMR is often silent). Never a hard filter.
SPEECH_PENALTY = 0.18
ARC_COMPLETE_BONUS = 0.7
ARC_PARTIAL_BONUS = 0.18
# SPEC-ANA-18: inverted capture order ranks below a partial-arc bonus.
ARC_ORDER_PENALTY = 0.15
CROSS_DAY_PENALTY = 0.08
DIVERSITY_BONUS = 0.08
MEDIA_DIVERSITY_BONUS = 0.06
SPATIAL_CONF_BOOST = 0.06
# Train F: pack enough spans to approach target without thin incomplete sheets.
DURATION_BAND_LO = 0.75
DURATION_BAND_HI = 1.17
TARGET_PACK_BONUS = 0.2


def normalize_style(style: str | None) -> str:
    text = (style or "process").strip().lower()
    if text in STYLES:
        return text
    return "process"


def clamp_target_s(target_s: float | None, style: str = "process") -> float:
    if style == "youtube":
        default = 600.0
    else:
        default = DEFAULT_TARGET_PROCESS_S if style == "process" else DEFAULT_TARGET_REEL_S
    if target_s is None:
        return default
    try:
        value = float(target_s)
    except (TypeError, ValueError):
        return default
    if value <= 0:
        return default
    maximum = MAX_TARGET_YOUTUBE_S if style == "youtube" else MAX_TARGET_S
    return max(MIN_TARGET_S, min(maximum, value))


def normalize_role(role: str | None) -> str:
    text = (role or "").strip().lower()
    if text == "polish":
        return "after"
    return text


def section_for_role(role: str, *, style: str = "process") -> str:
    role = normalize_role(role)
    if role in BEFORE_ROLES:
        return "before"
    if role in AFTER_ROLES:
        return "after"
    if role in HERO_ROLES:
        return "hero"
    if role in PROCESS_ROLES:
        return "process"
    if role in SKIP_ROLES:
        return "skip"
    if style == "reel":
        if role in REEL_HOOK:
            return "before"
        if role in REEL_JOURNEY:
            return "process"
        if role in REEL_SITE:
            return "process"
        if role in REEL_CLOSER:
            return "after"
    return "process"


def beat_floor_s(style: str, section: str) -> float:
    if style == "process":
        if section in {"before", "after", "hero"}:
            return max(SHOT_ACK_MIN_S, 4.0)
        return MIN_VIDEO_DURATION_S
    # reel: acknowledge floor, slightly longer for open/close
    if section in {"before", "after", "hero"}:
        return max(SHOT_ACK_MIN_S, 3.0)
    return SHOT_ACK_MIN_S


def beat_ideal_s(style: str, section: str) -> float:
    floor = beat_floor_s(style, section)
    if style == "process":
        if section == "process":
            return min(SHOT_MAX_S, max(floor, 6.5))
        if section == "before":
            return min(SHOT_MAX_S, max(floor, 5.0))
        if section == "after":
            return min(SHOT_MAX_S, max(floor, 5.5))
        return min(SHOT_MAX_S, max(floor, 4.5))
    if section == "process":
        return min(SHOT_MAX_S, max(floor, 3.5))
    return min(SHOT_MAX_S, max(floor, 3.2))


def _span_duration(card: dict) -> float:
    try:
        return max(0.0, float(card.get("out_s", 0.0)) - float(card.get("in_s", 0.0)))
    except (TypeError, ValueError):
        return 0.0


def _audio_class(card: dict) -> str:
    metrics = card.get("metrics") or {}
    if isinstance(metrics, dict) and metrics.get("audio_class"):
        return str(metrics.get("audio_class") or "").lower()
    reason = str(card.get("reason") or "").lower()
    if "speech" in reason:
        return "speech"
    return str(card.get("audio_class") or "").lower()


def _card_score(card: dict) -> float:
    try:
        return float(card.get("score") or 0.0)
    except (TypeError, ValueError):
        return 0.0


def _speech_penalty(card: dict, style: str) -> float:
    if style != "process":
        return 0.0
    if _audio_class(card) == "speech":
        return SPEECH_PENALTY
    return 0.0


def attach_focus_hint(card: dict, spatial_by_media: dict[str, dict] | None) -> dict | None:
    if not spatial_by_media:
        # Prefer hint already stamped on the card (refine/spatial path).
        hint = card.get("focus_hint")
        return hint if isinstance(hint, dict) else None
    mid = str(card.get("media_id") or "")
    payload = spatial_by_media.get(mid) or {}
    hint = pick_hint_for_span(
        payload,
        media_id=mid,
        in_s=float(card.get("in_s", 0.0) or 0.0),
        out_s=float(card.get("out_s", 0.0) or 0.0),
    )
    if hint is None:
        existing = card.get("focus_hint")
        return existing if isinstance(existing, dict) else None
    return hint


def materialize_beat(
    card: dict,
    *,
    style: str,
    duration_s: float,
    spatial_by_media: dict[str, dict] | None = None,
) -> dict:
    role = normalize_role(str(card.get("role_hint") or card.get("role") or "detail"))
    section = section_for_role(role, style=style)
    in_s = round(float(card.get("in_s", 0.0)), 4)
    span_len = _span_duration(card)
    # Prefer the head of the span (process ASMR holds), clamp to available source.
    hold = min(max(duration_s, 0.1), span_len if span_len > 1e-6 else duration_s)
    out_s = round(in_s + hold, 4)
    hint = attach_focus_hint(card, spatial_by_media)
    beat = {
        "role": role,
        "section": section,
        "media_id": card.get("media_id"),
        "in_s": in_s,
        "out_s": out_s,
        "duration_s": round(hold, 4),
        "score": round(_card_score(card), 4),
        "keyframe_path": card.get("keyframe_path") or card.get("keyframe") or "",
        "reason": card.get("reason") or f"role={role}",
        "source": card.get("source") or "understand",
        "shoot_day": card.get("shoot_day"),
        "media_role": card.get("media_role"),
        "captured_at": card.get("captured_at"),
    }
    if hint:
        beat["focus_hint"] = hint
    return beat


def _bucket_cards(cards: list[dict], style: str) -> dict[str, list[dict]]:
    buckets: dict[str, list[dict]] = {
        "before": [],
        "process": [],
        "after": [],
        "hero": [],
        "skip": [],
    }
    for card in cards:
        role = normalize_role(str(card.get("role_hint") or card.get("role") or ""))
        if not role:
            continue
        section = section_for_role(role, style=style)
        buckets.setdefault(section, []).append(card)
    for key, rows in buckets.items():
        rows.sort(
            key=lambda c: (
                -_card_score(c) + _speech_penalty(c, style),
                str(c.get("media_id") or ""),
                float(c.get("in_s") or 0.0),
            )
        )
    return buckets


def _card_key(card: dict) -> tuple:
    return (
        str(card.get("media_id") or ""),
        round(float(card.get("in_s") or 0.0), 2),
        round(float(card.get("out_s") or 0.0), 2),
    )


def _pick_diverse(process_cards: list[dict], n: int, style: str) -> list[dict]:
    """Greedy pick: prefer distinct roles and media, then score (speech-penalized)."""
    if n <= 0 or not process_cards:
        return []
    picked: list[dict] = []
    used_roles: set[str] = set()
    used_media: set[str] = set()
    used_keys: set[tuple] = set()

    def take(card: dict) -> None:
        picked.append(card)
        used_roles.add(normalize_role(str(card.get("role_hint") or card.get("role") or "")))
        mid = str(card.get("media_id") or "")
        if mid:
            used_media.add(mid)
        used_keys.add(_card_key(card))

    # Pass 1: unique roles.
    for card in process_cards:
        role = normalize_role(str(card.get("role_hint") or card.get("role") or ""))
        if role in used_roles:
            continue
        if _card_key(card) in used_keys:
            continue
        take(card)
        if len(picked) >= n:
            return picked
    # Pass 2: new media_ids (album packing across clips).
    for card in process_cards:
        if len(picked) >= n:
            break
        mid = str(card.get("media_id") or "")
        if mid and mid in used_media:
            continue
        if _card_key(card) in used_keys:
            continue
        take(card)
    # Pass 3: fill remaining by score (prefer longer usable spans).
    ranked = sorted(
        process_cards,
        key=lambda c: (
            -min(SHOT_MAX_S, _span_duration(c)),
            _speech_penalty(c, style) - _card_score(c),
            str(c.get("media_id") or ""),
            float(c.get("in_s") or 0.0),
        ),
    )
    for card in ranked:
        if len(picked) >= n:
            break
        if _card_key(card) in used_keys:
            continue
        take(card)
    return picked


def _mean_usable_span(cards: list[dict]) -> float:
    if not cards:
        return beat_ideal_s("process", "process")
    lengths = [min(SHOT_MAX_S, max(0.5, _span_duration(c))) for c in cards]
    return sum(lengths) / len(lengths)


def process_count_for_target(
    target_s: float,
    *,
    style: str,
    process_cards: list[dict],
    has_before: bool,
    has_after: bool,
    include_hero: bool,
    has_hero: bool,
    requested: int | None = None,
) -> int:
    """How many process spans to pack so duration can approach target_s."""
    if not process_cards:
        return 0
    reserved = 0.0
    if has_before:
        reserved += beat_floor_s(style, "before")
    if has_after:
        reserved += beat_floor_s(style, "after")
    if include_hero and has_hero:
        reserved += beat_floor_s(style, "hero")
    remain = max(0.0, float(target_s) - reserved)
    mean_span = max(beat_floor_s(style, "process"), _mean_usable_span(process_cards))
    needed = max(1, int(round(remain / mean_span))) if remain > 0 else 1
    # Prefer a real ASMR middle when bookends exist.
    if has_before and has_after:
        needed = max(needed, 2)
    cap = len(process_cards)
    if requested is not None:
        needed = max(needed, int(requested))
    return max(1, min(cap, needed))


def _allocate_durations(
    sections: list[str],
    *,
    style: str,
    target_s: float,
    span_limits: list[float],
) -> list[float]:
    if not sections:
        return []
    ideals = [beat_ideal_s(style, sec) for sec in sections]
    floors = [beat_floor_s(style, sec) for sec in sections]
    # Cap by available source span when known (never above SHOT_MAX_S).
    caps = []
    for i, lim in enumerate(span_limits):
        span_cap = lim if lim > 1e-6 else SHOT_MAX_S
        caps.append(max(floors[i], min(SHOT_MAX_S, span_cap)))
    # Start at floors; grow toward ideals; then trim/grow to target.
    durs = [min(caps[i], max(floors[i], min(ideals[i], caps[i]))) for i in range(len(sections))]
    total = sum(durs)
    if total < target_s - 1e-6:
        # Grow process middle first, then after, before, hero.
        order = sorted(
            range(len(sections)),
            key=lambda i: (
                0 if sections[i] == "process" else 1 if sections[i] == "after" else 2,
                i,
            ),
        )
        guard = 0
        while sum(durs) < target_s - 1e-6 and guard < 500:
            progressed = False
            for i in order:
                room = caps[i] - durs[i]
                if room <= 1e-6:
                    continue
                step = min(room, 0.5, target_s - sum(durs))
                if step <= 1e-6:
                    continue
                durs[i] += step
                progressed = True
                if sum(durs) >= target_s - 1e-6:
                    break
            if not progressed:
                break
            guard += 1
    elif total > target_s + 1e-6:
        # Shrink from the middle first while respecting floors.
        order = sorted(
            range(len(sections)),
            key=lambda i: (
                0 if sections[i] == "process" else 1 if sections[i] == "hero" else 2,
                -i,
            ),
        )
        guard = 0
        while sum(durs) > target_s + 1e-6 and guard < 500:
            progressed = False
            for i in order:
                room = durs[i] - floors[i]
                if room <= 1e-6:
                    continue
                step = min(room, 0.5, sum(durs) - target_s)
                if step <= 1e-6:
                    continue
                durs[i] -= step
                progressed = True
                if sum(durs) <= target_s + 1e-6:
                    break
            if not progressed:
                break
            guard += 1
    return [round(d, 4) for d in durs]


def _arc_label(roles: list[str]) -> str:
    return "→".join(roles)


def _score_candidate(
    beats: list[dict],
    *,
    style: str,
    target_s: float,
) -> tuple[float, str, bool]:
    if not beats:
        return 0.0, "empty", False
    sections = {b["section"] for b in beats}
    has_before = "before" in sections
    has_process = "process" in sections
    # after-class includes after/polish and hero (Train G acceptance).
    has_after = "after" in sections or "hero" in sections
    complete = has_before and has_process and has_after
    partial = (has_before and has_after) or (has_process and has_after) or (has_before and has_process)

    mean = sum(float(b.get("score") or 0.0) for b in beats) / len(beats)
    speech_hits = sum(1 for b in beats if "speech" in str(b.get("reason") or "").lower())
    # Prefer silent/ambient process ASMR; speech is a soft ding only.
    speech_cost = SPEECH_PENALTY * (speech_hits / len(beats)) if style == "process" else 0.0
    roles = [str(b.get("role") or "") for b in beats if b.get("section") == "process"]
    diversity = DIVERSITY_BONUS * (len(set(roles)) / max(1, len(roles))) if roles else 0.0
    media_ids = [str(b.get("media_id") or "") for b in beats if b.get("media_id")]
    media_div = (
        MEDIA_DIVERSITY_BONUS * (len(set(media_ids)) / max(1, len(media_ids))) if media_ids else 0.0
    )
    spatial = 0.0
    for b in beats:
        hint = b.get("focus_hint") or {}
        if isinstance(hint, dict):
            spatial += SPATIAL_CONF_BOOST * float(hint.get("confidence") or 0.0)
    spatial /= max(1, len(beats))

    duration = sum(float(b.get("duration_s") or 0.0) for b in beats)
    length_fit = max(0.0, 1.0 - abs(duration - target_s) / max(target_s, 1.0)) * 0.15
    in_band = DURATION_BAND_LO * target_s <= duration <= DURATION_BAND_HI * target_s
    pack_bonus = TARGET_PACK_BONUS if (complete and in_band) else 0.0
    # Thin incomplete sheets (e.g. engine→wash at ~14s for a 60s target) rank down hard.
    thin_penalty = 0.0
    if style == "process" and target_s >= 40.0 and duration < target_s * 0.4:
        thin_penalty = 0.35
    if style == "process" and not complete:
        thin_penalty += 0.2

    bonus = ARC_COMPLETE_BONUS if complete else (ARC_PARTIAL_BONUS if partial else 0.0)
    score = mean + bonus + diversity + media_div + spatial + length_fit + pack_bonus - speech_cost - thin_penalty

    if complete:
        reason = "transformation arc: before → process ASMR → after"
    elif has_before and has_after:
        reason = "partial arc: before → after (thin process middle)"
    elif has_process and has_after:
        reason = "partial arc: process → after"
    elif has_before and has_process:
        reason = "partial arc: before → process"
    else:
        reason = "ranked spans (incomplete transformation arc)"
    if style == "reel" and complete:
        reason = "reel target with transformation arc (not transcript/virality)"
    if complete and in_band:
        reason = f"{reason}; packed toward {target_s:.0f}s"
    return round(score, 4), reason, complete


def _apply_media_role_bookends(cards: list[dict]) -> list[dict]:
    """When media is tagged before/after, prefer that label over monopoly hints."""
    out: list[dict] = []
    monopoly = frozenset({"wash", "skip_face", "hero", "engine"})
    for card in cards:
        media_role = normalize_role(str(card.get("media_role") or ""))
        role_hint = normalize_role(str(card.get("role_hint") or card.get("role") or ""))
        if media_role in BEFORE_ROLES and role_hint in monopoly | PROCESS_ROLES:
            out.append({**card, "role_hint": "before"})
        elif media_role in AFTER_ROLES and role_hint in monopoly | PROCESS_ROLES | BEFORE_ROLES:
            out.append({**card, "role_hint": "after"})
        elif media_role == "polish" and role_hint in monopoly | PROCESS_ROLES | BEFORE_ROLES:
            out.append({**card, "role_hint": "after"})
        else:
            out.append(card)
    return out


def _album_key(card: dict) -> tuple:
    idx = card.get("media_index")
    try:
        order = int(idx) if idx is not None else 10_000
    except (TypeError, ValueError):
        order = 10_000
    return (order, float(card.get("in_s") or 0.0), str(card.get("media_id") or ""))


def _ensure_soft_bookends(cards: list[dict]) -> list[dict]:
    """Train G: promote earliest/latest monopoly spans to before/after when missing.

    Does not invent duplicate wash padding. Prefer media_tag / existing labels.
    """
    if len(cards) < 2:
        return list(cards)
    roles = {normalize_role(str(c.get("role_hint") or c.get("role") or "")) for c in cards}
    has_before = bool(roles & BEFORE_ROLES)
    has_after = bool(roles & (AFTER_ROLES | HERO_ROLES))
    if has_before and has_after:
        return list(cards)
    ordered = sorted(cards, key=_album_key)
    out = [dict(c) for c in cards]
    by_key = {_card_key(c): i for i, c in enumerate(out)}

    def promote(card: dict, role: str) -> None:
        idx = by_key.get(_card_key(card))
        if idx is None:
            return
        updated = dict(out[idx])
        updated["role_hint"] = role
        reason = str(updated.get("reason") or "")
        note = f"soft_bookend→{role}"
        updated["reason"] = f"{reason}; {note}" if reason else note
        out[idx] = updated

    stealable = PROCESS_ROLES | frozenset({"wash", "skip_face", "hero", "engine", "machine"})
    if not has_before:
        for card in ordered:
            role = normalize_role(str(card.get("role_hint") or card.get("role") or ""))
            if role in stealable and role not in AFTER_ROLES:
                promote(card, "before")
                break
    if not has_after:
        for card in reversed(ordered):
            role = normalize_role(str(card.get("role_hint") or card.get("role") or ""))
            # Re-read after possible before promotion.
            idx = by_key.get(_card_key(card))
            if idx is not None:
                role = normalize_role(str(out[idx].get("role_hint") or ""))
            if role in BEFORE_ROLES:
                continue
            if role in stealable or role in PROCESS_ROLES:
                promote(card, "after")
                break
    return out


def build_candidate_sheet(
    cards: list[dict],
    *,
    target_s: float,
    style: str = "process",
    process_count: int = 3,
    include_hero: bool = False,
    spatial_by_media: dict[str, dict] | None = None,
) -> dict | None:
    """One ranked beat sheet packed toward target_s. None if no usable cards."""
    style = normalize_style(style)
    target = clamp_target_s(target_s, style)
    cards = _ensure_soft_bookends(_apply_media_role_bookends(cards))
    buckets = _bucket_cards(cards, style)
    selected: list[dict] = []

    if buckets["before"]:
        selected.append(buckets["before"][0])

    fit = process_count_for_target(
        target,
        style=style,
        process_cards=buckets["process"],
        has_before=bool(buckets["before"]),
        has_after=bool(buckets["after"]),
        include_hero=include_hero,
        has_hero=bool(buckets["hero"]),
        requested=process_count,
    )
    if fit:
        selected.extend(_pick_diverse(buckets["process"], fit, style))
    if buckets["after"]:
        selected.append(buckets["after"][0])
    if include_hero and buckets["hero"]:
        selected.append(buckets["hero"][0])

    if not selected:
        # Last resort: take top scored cards in story order.
        ranked = sorted(
            cards,
            key=lambda c: (
                PROCESS_STORY_ORDER.index(normalize_role(str(c.get("role_hint") or c.get("role") or "")))
                if normalize_role(str(c.get("role_hint") or c.get("role") or "")) in PROCESS_STORY_ORDER
                else 99,
                -_card_score(c),
            ),
        )
        selected = ranked[: max(1, min(4, len(ranked)))]
    if not selected:
        return None

    # Deduplicate identical spans (keep first: before → process → after order).
    deduped: list[dict] = []
    seen: set[tuple] = set()
    for card in selected:
        key = _card_key(card)
        if key in seen:
            continue
        seen.add(key)
        deduped.append(card)
    selected = deduped

    # Refuse wash-only padding pretending to be a transformation arc.
    sections_preview = [
        section_for_role(
            normalize_role(str(c.get("role_hint") or c.get("role") or "")),
            style=style,
        )
        for c in selected
    ]
    if (
        style == "process"
        and "before" not in sections_preview
        and "after" not in sections_preview
        and sections_preview
        and all(s == "process" for s in sections_preview)
    ):
        # Soft bookends should have fired; if still process-only, force ends.
        selected = _ensure_soft_bookends(selected)
        if selected:
            first = dict(selected[0])
            first["role_hint"] = "before"
            selected[0] = first
            last = dict(selected[-1])
            if normalize_role(str(last.get("role_hint") or "")) != "before":
                last["role_hint"] = "after"
                selected[-1] = last

    sections = [
        section_for_role(
            normalize_role(str(c.get("role_hint") or c.get("role") or "")),
            style=style,
        )
        for c in selected
    ]
    limits = [_span_duration(c) for c in selected]
    durs = _allocate_durations(sections, style=style, target_s=target, span_limits=limits)
    beats = [
        materialize_beat(card, style=style, duration_s=durs[i], spatial_by_media=spatial_by_media)
        for i, card in enumerate(selected)
    ]
    score, reason, complete = _score_candidate(beats, style=style, target_s=target)
    order_ok, cross_day, order_notes = beats_arc_order(beats)
    if not order_ok:
        score = round(score - ARC_ORDER_PENALTY, 4)
        reason = f"{reason}; capture-order inverted"
    elif cross_day:
        score = round(score - CROSS_DAY_PENALTY, 4)
        reason = f"{reason}; cross-day bookends"
    if order_notes and not order_ok:
        reason = f"{reason} ({order_notes[0]})"
    roles = [str(b.get("role") or "") for b in beats]
    return {
        "score": score,
        "duration_s": round(sum(float(b["duration_s"]) for b in beats), 4),
        "arc": _arc_label(roles),
        "arc_complete": complete,
        "arc_order_ok": order_ok,
        "reason": reason,
        "beats": beats,
        "style": style,
        "target_s": target,
    }


def suggest_highlight_sheets(
    cards: list[dict],
    *,
    target_s: float,
    style: str = "process",
    spatial_by_media: dict[str, dict] | None = None,
    max_candidates: int = MAX_CANDIDATES,
) -> list[dict]:
    """Ranked candidate beat sheets. Highest score first. Suggest-only."""
    style = normalize_style(style)
    target = clamp_target_s(target_s, style)
    prepared = _ensure_soft_bookends(_apply_media_role_bookends(cards))
    buckets = _bucket_cards(prepared, style)
    auto_n = process_count_for_target(
        target,
        style=style,
        process_cards=buckets["process"],
        has_before=bool(buckets["before"]),
        has_after=bool(buckets["after"]),
        include_hero=False,
        has_hero=bool(buckets["hero"]),
        requested=None,
    )
    variants: list[tuple[int, bool, str]] = []
    if style == "process":
        variants = [
            (max(3, auto_n), False, "primary_pack"),
            (max(4, auto_n + 1), False, "rich_process"),
            (max(2, auto_n - 1), True, "compact_hero"),
            (max(5, auto_n), True, "long_hero"),
            (max(2, min(3, auto_n)), False, "compact"),
            (1, False, "minimal"),
        ]
    else:
        variants = [
            (max(2, min(auto_n, 4)), False, "primary"),
            (max(3, min(auto_n, 5)), False, "rich"),
            (1, True, "hook_hero"),
            (2, True, "reel_hero"),
            (1, False, "minimal"),
        ]

    sheets: list[dict] = []
    seen_arcs: set[str] = set()
    for process_count, include_hero, _label in variants:
        sheet = build_candidate_sheet(
            prepared,
            target_s=target,
            style=style,
            process_count=process_count,
            include_hero=include_hero,
            spatial_by_media=spatial_by_media,
        )
        if sheet is None:
            continue
        # Dedupe near-identical arcs.
        sig = "|".join(
            f"{b['media_id']}:{b['role']}:{b['in_s']:.1f}" for b in sheet["beats"]
        )
        if sig in seen_arcs:
            continue
        seen_arcs.add(sig)
        sheets.append(sheet)

    # Prefer complete arcs packed near target, then score.
    sheets.sort(
        key=lambda s: (
            -int(s["arc_complete"]),
            -float(s["score"]),
            abs(float(s["duration_s"]) - target),
        )
    )
    out: list[dict] = []
    for i, sheet in enumerate(sheets[: max(1, max_candidates)]):
        row = dict(sheet)
        row["rank"] = i + 1
        out.append(row)
    return out


__all__ = [
    "AFTER_ROLES",
    "BEFORE_ROLES",
    "DEFAULT_TARGET_PROCESS_S",
    "DEFAULT_TARGET_REEL_S",
    "HERO_ROLES",
    "MAX_CANDIDATES",
    "MAX_TARGET_S",
    "MIN_TARGET_S",
    "PROCESS_ROLES",
    "STYLES",
    "attach_focus_hint",
    "beat_floor_s",
    "beat_ideal_s",
    "build_candidate_sheet",
    "clamp_target_s",
    "materialize_beat",
    "normalize_role",
    "normalize_style",
    "process_count_for_target",
    "section_for_role",
    "suggest_highlight_sheets",
]
