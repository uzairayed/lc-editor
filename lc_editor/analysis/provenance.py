"""SPEC-ANA-18 / SPEC-ANA-19: capture provenance and album cards.

Inference proposes. Capture time and confirmed cards dispose.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path

from lc_editor.analysis.media import (
    normalize_role,
    normalize_shoot_day,
    parse_captured_at,
    shoot_days_equal,
)
from lc_editor.analysis.rank import UNDERSTAND_TAG_PREFIX

DAY_GAP = timedelta(hours=4)
ROLE_MARGIN_CONFIRM = 0.08
FOLDER_HINT_CONFIDENCE = 0.7
ARC_BOOKEND_ROLES = frozenset({"before", "after", "polish", "hero"})
BEFORE_ROLES = frozenset({"before"})
AFTER_ROLES = frozenset({"after", "polish", "hero"})
PATH_ROLE_TOKENS = frozenset(
    {"before", "after", "wash", "interior", "wheel", "engine", "hero", "polish", "machine", "detail"}
)
DAY_TOKEN = re.compile(r"^(?:day|d)(\d+)$", re.IGNORECASE)
TOKEN_SPLIT = re.compile(r"[^A-Za-z0-9]+")


@dataclass
class DayCluster:
    shoot_day: int
    media_ids: list[str] = field(default_factory=list)
    start_at: str | None = None
    end_at: str | None = None
    cover_keyframe: str | None = None


@dataclass
class PathHints:
    shoot_day: int | None = None
    role: str | None = None


def _as_aware(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value


def _media_id(item) -> str:
    return str(getattr(item, "id", "") or "")


def _media_captured(item) -> str | None:
    return getattr(item, "captured_at", None)


def _media_attr(item, name: str, default=None):
    if hasattr(item, name):
        return getattr(item, name)
    if isinstance(item, dict):
        return item.get(name, default)
    return default


def hints_from_path(path: str | Path) -> PathHints:
    """Whole-segment / token matches only. ``day1`` / ``d2`` → day; role folder names."""
    raw = Path(path)
    tokens: list[str] = []
    for part in raw.parts:
        stem = Path(part).stem if Path(part).suffix else part
        tokens.extend(tok for tok in TOKEN_SPLIT.split(stem) if tok)
    shoot_day: int | None = None
    role: str | None = None
    for token in tokens:
        day_match = DAY_TOKEN.match(token)
        if day_match and shoot_day is None:
            shoot_day = int(day_match.group(1))
            continue
        lowered = token.lower()
        if role is None and lowered in PATH_ROLE_TOKENS:
            role = "after" if lowered == "polish" else lowered
    return PathHints(shoot_day=shoot_day, role=role)


def cluster_shoot_days(media: list) -> tuple[list[DayCluster], list[str]]:
    """Group dated media. New day on local date change or a gap > 4 hours."""
    dated: list[tuple[datetime, object]] = []
    unclustered: list[str] = []
    for item in media:
        parsed = parse_captured_at(_media_captured(item))
        if parsed is None:
            mid = _media_id(item)
            if mid:
                unclustered.append(mid)
            continue
        dated.append((_as_aware(parsed), item))
    dated.sort(key=lambda pair: (pair[0], _media_id(pair[1])))
    clusters: list[DayCluster] = []
    current: list[tuple[datetime, object]] = []
    for stamp, item in dated:
        if current:
            prev_stamp, _ = current[-1]
            new_day = stamp.date() != prev_stamp.date() or (stamp - prev_stamp) > DAY_GAP
            if new_day:
                clusters.append(_cluster_from_rows(len(clusters) + 1, current))
                current = []
        current.append((stamp, item))
    if current:
        clusters.append(_cluster_from_rows(len(clusters) + 1, current))
    return clusters, unclustered


def _cluster_from_rows(day: int, rows: list[tuple[datetime, object]]) -> DayCluster:
    start = rows[0][0].strftime("%Y-%m-%dT%H:%M:%SZ")
    end = rows[-1][0].strftime("%Y-%m-%dT%H:%M:%SZ")
    return DayCluster(
        shoot_day=day,
        media_ids=[_media_id(item) for _, item in rows],
        start_at=start,
        end_at=end,
    )


def day_for_media(media_id: str, clusters: list[DayCluster]) -> int | None:
    for cluster in clusters:
        if media_id in cluster.media_ids:
            return cluster.shoot_day
    return None


def role_margin(role_scores: dict | None, role: str | None) -> float | None:
    if not role_scores or not role:
        return None
    try:
        best = float(role_scores.get(role) or 0.0)
    except (TypeError, ValueError):
        return None
    others = []
    for name, score in role_scores.items():
        if str(name) == str(role):
            continue
        try:
            others.append(float(score))
        except (TypeError, ValueError):
            continue
    if not others:
        return None
    return best - max(others)


def normalize_process_role(role: str | None) -> str | None:
    text = normalize_role(role)
    if text == "polish":
        return "after"
    return text


def is_before_role(role: str | None) -> bool:
    return normalize_process_role(role) in BEFORE_ROLES


def is_after_role(role: str | None) -> bool:
    return normalize_process_role(role) in AFTER_ROLES


def understand_role_from_tags(tags: list[str] | None) -> str | None:
    for tag in tags or []:
        text = str(tag)
        if text.startswith(UNDERSTAND_TAG_PREFIX):
            role = normalize_process_role(text[len(UNDERSTAND_TAG_PREFIX) :])
            if role:
                return role
    return None


def resolve_slot_role(
    *,
    media_role: str | None,
    card_role: str | None,
    understand_role: str | None,
) -> str | None:
    """Media tag first, then confirmed/proposed card, then understand span."""
    tagged = normalize_process_role(media_role)
    if tagged:
        return tagged
    carded = normalize_process_role(card_role)
    if carded:
        return carded
    return normalize_process_role(understand_role)


def contrasting_keyframes(shots: list, limit: int = 3) -> list[str]:
    """2–3 contrasting JPEG paths: darkest, brightest, sharpest/most motion."""
    usable = [shot for shot in shots if getattr(shot, "keyframe", None)]
    if not usable:
        return []
    picked: list[object] = []
    seen: set[str] = set()

    def take(shot) -> None:
        key = str(getattr(shot, "id", "") or shot.keyframe)
        if key in seen:
            return
        seen.add(key)
        picked.append(shot)

    take(min(usable, key=lambda s: (s.metrics.luma_mean, s.id)))
    take(max(usable, key=lambda s: (s.metrics.luma_mean, s.id)))
    if len(picked) < limit:
        take(max(usable, key=lambda s: (s.metrics.motion, s.metrics.sharpness, s.id)))
    if len(picked) < limit:
        take(max(usable, key=lambda s: (s.metrics.sharpness, s.id)))
    return [shot.keyframe for shot in picked[:limit]]


def best_understand_card(cards: list[dict]) -> dict | None:
    if not cards:
        return None
    return max(
        cards,
        key=lambda card: (
            float(card.get("score") or 0.0),
            str(card.get("role_hint") or ""),
        ),
    )


def capture_contradicts_role(
    *,
    proposed_role: str | None,
    captured_at: str | None,
    peers: list,
) -> bool:
    """True when an after is earlier than a before (or the reverse) in the album."""
    stamp = parse_captured_at(captured_at)
    role = normalize_process_role(proposed_role)
    if stamp is None or role is None:
        return False
    stamp = _as_aware(stamp)
    for peer in peers:
        peer_role = normalize_process_role(_media_attr(peer, "role"))
        peer_stamp = parse_captured_at(_media_attr(peer, "captured_at"))
        if peer_stamp is None or peer_role is None:
            continue
        peer_stamp = _as_aware(peer_stamp)
        if is_after_role(role) and is_before_role(peer_role) and stamp < peer_stamp:
            return True
        if is_before_role(role) and is_after_role(peer_role) and stamp > peer_stamp:
            return True
    return False


def propose_question(
    *,
    proposed_role: str | None,
    runner_up: str | None,
    shoot_day: int | str | None,
    contradicts: bool,
    luma_mean: float | None,
) -> str | None:
    if not proposed_role:
        return "what is in frame — before, wash, or after?"
    if contradicts and is_after_role(proposed_role):
        day = shoot_day if shoot_day is not None else "?"
        return (
            f"bright sharp panel but captured on day {day} before wash spans — before or after?"
        )
    if contradicts and is_before_role(proposed_role):
        return "labeled before but captured after a later polish span — before or after?"
    if runner_up and proposed_role:
        if luma_mean is not None and luma_mean >= 0.55 and is_before_role(proposed_role):
            return (
                f"bright sharp panel scoring {proposed_role} (close to {runner_up}) — "
                "before or after?"
            )
        return f"close scores: {proposed_role} vs {runner_up} — which role?"
    return None


def card_coverage(media: list) -> dict:
    visual = [item for item in media if _media_attr(item, "kind") != "audio"]
    carded = 0
    for item in visual:
        card = _media_attr(item, "card")
        confirmed = bool(getattr(card, "confirmed", False)) if card is not None else False
        if isinstance(card, dict):
            confirmed = bool(card.get("confirmed"))
        if confirmed:
            carded += 1
    return {"carded": carded, "total": len(visual)}


def is_carded(item) -> bool:
    card = _media_attr(item, "card")
    if card is None:
        return False
    if isinstance(card, dict):
        return bool(card.get("confirmed"))
    return bool(getattr(card, "confirmed", False))


def confirmed_roles_map(media: list) -> dict[str, str | None]:
    out: dict[str, str | None] = {}
    for item in media:
        card = _media_attr(item, "card")
        if card is None:
            continue
        confirmed = card.get("confirmed") if isinstance(card, dict) else getattr(card, "confirmed", False)
        role = card.get("role") if isinstance(card, dict) else getattr(card, "role", None)
        if confirmed and role:
            out[_media_id(item)] = normalize_process_role(role)
    return out


def beats_arc_order(beats: list[dict]) -> tuple[bool, bool, list[str]]:
    """Return (order_ok, cross_day, notes) for a suggested beat sheet."""
    befores: list[tuple[datetime, dict]] = []
    afters: list[tuple[datetime, dict]] = []
    notes: list[str] = []
    for beat in beats:
        role = normalize_process_role(str(beat.get("role") or beat.get("section") or ""))
        stamp = parse_captured_at(beat.get("captured_at"))
        if stamp is None:
            continue
        stamp = _as_aware(stamp)
        if is_before_role(role):
            befores.append((stamp, beat))
        elif is_after_role(role):
            afters.append((stamp, beat))
    order_ok = True
    for after_stamp, after_beat in afters:
        for before_stamp, before_beat in befores:
            if after_stamp < before_stamp:
                order_ok = False
                notes.append(
                    f"after {after_beat.get('media_id')} captured before "
                    f"before {before_beat.get('media_id')}"
                )
    cross_day = False
    for _, after_beat in afters:
        after_day = after_beat.get("shoot_day")
        for _, before_beat in befores:
            before_day = before_beat.get("shoot_day")
            if after_day is None or before_day is None:
                continue
            if not shoot_days_equal(after_day, before_day):
                cross_day = True
                notes.append("cross-day bookends")
    return order_ok, cross_day, notes


def arc_order_issues(slots: list[dict]) -> list[str]:
    """``slots`` are {clip_id, media_id, role, captured_at}."""
    befores: list[dict] = []
    afters: list[dict] = []
    for slot in slots:
        role = normalize_process_role(slot.get("role"))
        if is_before_role(role):
            befores.append(slot)
        elif is_after_role(role):
            afters.append(slot)
    issues: list[str] = []
    seen: set[str] = set()
    for after in afters:
        after_stamp = parse_captured_at(after.get("captured_at"))
        if after_stamp is None:
            continue
        after_stamp = _as_aware(after_stamp)
        for before in befores:
            before_stamp = parse_captured_at(before.get("captured_at"))
            if before_stamp is None:
                continue
            before_stamp = _as_aware(before_stamp)
            if after_stamp < before_stamp:
                key = f"{after.get('clip_id')}:{before.get('clip_id')}"
                if key in seen:
                    continue
                seen.add(key)
                issues.append(
                    f"SPEC-ANA-18: clip {after.get('clip_id')} "
                    f"({normalize_process_role(after.get('role'))}) captured before "
                    f"clip {before.get('clip_id')} (before)"
                )
    return issues


def uncarded_slot_issues(slots: list[dict], media_by_id: dict) -> list[str]:
    issues: list[str] = []
    for slot in slots:
        role = normalize_process_role(slot.get("role"))
        if role not in {"before", "after"}:
            continue
        item = media_by_id.get(slot.get("media_id"))
        if item is None or is_carded(item):
            continue
        issues.append(
            f"SPEC-ANA-19: clip {slot.get('clip_id')} fills '{role}' "
            f"from uncarded media {slot.get('media_id')}"
        )
    return issues


def propose_card(
    item,
    *,
    understand_cards: list[dict] | None = None,
    shots: list | None = None,
    cluster_day: int | str | None = None,
    peers: list | None = None,
) -> dict:
    """One proposed album card. Read-only helper; Editor persists on confirm."""
    hints = hints_from_path(_media_attr(item, "original_path") or _media_attr(item, "path") or "")
    existing_card = _media_attr(item, "card")
    existing_role = normalize_process_role(_media_attr(item, "role"))
    existing_day = normalize_shoot_day(_media_attr(item, "shoot_day"))
    confirmed = is_carded(item)
    best = best_understand_card(understand_cards or [])
    role_scores = (best or {}).get("role_scores") or {}
    understand_role = normalize_process_role((best or {}).get("role_hint"))
    proposed_role = existing_role or hints.role or understand_role
    if existing_card is not None:
        card_role = normalize_process_role(
            existing_card.get("role") if isinstance(existing_card, dict) else getattr(existing_card, "role", None)
        )
        proposed_role = card_role or proposed_role
    proposed_day = existing_day if existing_day is not None else hints.shoot_day
    if proposed_day is None:
        proposed_day = cluster_day

    margin = role_margin(role_scores, understand_role or proposed_role)
    runner_up = None
    if role_scores:
        ranked = sorted(
            ((str(name), float(score)) for name, score in role_scores.items()),
            key=lambda kv: (-kv[1], kv[0]),
        )
        if len(ranked) > 1:
            runner_up = ranked[1][0]
    close = margin is not None and margin <= ROLE_MARGIN_CONFIRM
    contradicts = capture_contradicts_role(
        proposed_role=proposed_role,
        captured_at=_media_captured(item),
        peers=peers or [],
    )
    luma = None
    if shots:
        luma = sum(s.metrics.luma_mean for s in shots) / len(shots)
    elif best and "luma" in str(best.get("reason") or ""):
        luma = 0.6 if "bright" in str(best.get("reason") or "") else None

    confidence = 1.0 if confirmed else 0.35
    if confirmed:
        pass
    elif hints.role or hints.shoot_day is not None:
        confidence = FOLDER_HINT_CONFIDENCE
        if existing_role:
            confidence = 0.8
    elif margin is not None:
        confidence = max(0.2, min(0.9, 0.45 + margin))
    elif proposed_role:
        confidence = 0.4

    needs = (not confirmed) and (close or contradicts or proposed_role is None)
    question = None
    if needs:
        question = propose_question(
            proposed_role=proposed_role,
            runner_up=runner_up,
            shoot_day=proposed_day,
            contradicts=contradicts,
            luma_mean=luma,
        )
    source = "suggested"
    if confirmed:
        source = (
            existing_card.get("source")
            if isinstance(existing_card, dict)
            else getattr(existing_card, "source", "agent")
        ) or "agent"
    elif hints.role or hints.shoot_day is not None:
        source = "folder"

    return {
        "media_id": _media_id(item),
        "proposed_role": proposed_role,
        "proposed_day": proposed_day,
        "confidence": round(float(confidence), 4),
        "keyframes": contrasting_keyframes(shots or []),
        "needs_confirmation": needs,
        "question": question,
        "source": source,
        "confirmed": confirmed,
        "role_scores": role_scores,
        "margin": None if margin is None else round(float(margin), 4),
        "path_hints": {"shoot_day": hints.shoot_day, "role": hints.role},
        "reason": (best or {}).get("reason") or "",
    }


__all__ = [
    "AFTER_ROLES",
    "ARC_BOOKEND_ROLES",
    "BEFORE_ROLES",
    "DAY_GAP",
    "DayCluster",
    "FOLDER_HINT_CONFIDENCE",
    "PATH_ROLE_TOKENS",
    "PathHints",
    "ROLE_MARGIN_CONFIRM",
    "arc_order_issues",
    "beats_arc_order",
    "best_understand_card",
    "card_coverage",
    "capture_contradicts_role",
    "cluster_shoot_days",
    "confirmed_roles_map",
    "contrasting_keyframes",
    "day_for_media",
    "hints_from_path",
    "is_after_role",
    "is_before_role",
    "is_carded",
    "normalize_process_role",
    "propose_card",
    "propose_question",
    "resolve_slot_role",
    "role_margin",
    "uncarded_slot_issues",
    "understand_role_from_tags",
]
