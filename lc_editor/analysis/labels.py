"""Resolved labels for the GUI and MCP. Inference proposes; confirmed cards dispose.

Precedence: confirmed shot override → confirmed media card → analysis → folder hint.
"""

from __future__ import annotations

from lc_editor.analysis.media import normalize_shoot_day, roles_equal, shoot_days_equal
from lc_editor.analysis.provenance import (
    ARC_BOOKEND_ROLES,
    capture_contradicts_role,
    hints_from_path,
    is_carded,
    normalize_process_role,
    propose_card,
    understand_role_from_tags,
)
from lc_editor.models import QUEUE_FILTERS, MediaItem, ShotCard

LABEL_UNDO_MAX = 50
GUI_DOMAIN_TOOLS = (
    "label_queue",
    "label_get",
    "shot_card_confirm",
    "labels_bulk_confirm",
    "labels_clear",
    "labels_undo",
    "label_conflicts",
    "label_readiness",
    "media_list",
    "shots_list",
    "media_proxy",
    "media_card_confirm",
    "media_card_propose",
    "media_remove",
)


def _shot_attr(shot, name, default=None):
    if shot is None:
        return default
    if isinstance(shot, dict):
        return shot.get(name, default)
    return getattr(shot, name, default)


def field(value, source: str | None, confirmed: bool = False) -> dict:
    return {"value": value, "source": source, "confirmed": bool(confirmed and value is not None)}


def understand_card_for_shot(shot, cards: list[dict] | None) -> dict | None:
    if shot is None:
        return None
    in_s = float(_shot_attr(shot, "in_s", 0.0) or 0.0)
    out_s = float(_shot_attr(shot, "out_s", 0.0) or 0.0)
    best = None
    best_score = -1.0
    for card in cards or []:
        if not isinstance(card, dict):
            continue
        cin = float(card.get("in_s", 0.0) or 0.0)
        cout = float(card.get("out_s", 0.0) or 0.0)
        if cout <= in_s or cin >= out_s:
            continue
        try:
            score = float(card.get("score") or 0.0)
        except (TypeError, ValueError):
            score = 0.0
        if score >= best_score:
            best = card
            best_score = score
    return best


def analysis_role(shot, understand_cards: list[dict] | None) -> str | None:
    card = understand_card_for_shot(shot, understand_cards)
    if card:
        hinted = normalize_process_role(card.get("role_hint") or card.get("role"))
        if hinted:
            return hinted
    return understand_role_from_tags(_shot_attr(shot, "tags"))


def folder_hints(item: MediaItem | None) -> tuple[str | None, int | str | None]:
    if item is None:
        return None, None
    card = item.card
    if card is not None and getattr(card, "source", None) == "folder" and not is_carded(item):
        return normalize_process_role(card.role), normalize_shoot_day(card.shoot_day)
    hints = hints_from_path(item.original_path or item.path or "")
    return normalize_process_role(hints.role), normalize_shoot_day(hints.shoot_day)


def resolve_labels(
    item: MediaItem | None,
    shot=None,
    *,
    shot_card: ShotCard | None = None,
    understand_cards: list[dict] | None = None,
    peers: list | None = None,
) -> dict:
    """Return role / day / subjects / note with source + confirmation for one scope."""
    media_id = item.id if item is not None else str(_shot_attr(shot, "media_id") or "")
    shot_id = str(_shot_attr(shot, "id") or "") or None
    folder_role, folder_day = folder_hints(item)
    analysis = analysis_role(shot, understand_cards)
    if analysis is None and shot is None and understand_cards:
        top = max(
            understand_cards,
            key=lambda card: float(card.get("score") or 0.0) if isinstance(card, dict) else 0.0,
            default=None,
        )
        if isinstance(top, dict):
            analysis = normalize_process_role(top.get("role_hint") or top.get("role"))

    media_card = item.card if item is not None else None
    media_confirmed = is_carded(item) if item is not None else False
    shot_confirmed = bool(shot_card is not None and shot_card.confirmed)

    role = field(None, None, False)
    if shot_confirmed and shot_card and shot_card.role:
        role = field(normalize_process_role(shot_card.role), "shot_card", True)
    elif media_confirmed and media_card and media_card.role:
        role = field(normalize_process_role(media_card.role), "media_card", True)
    elif analysis:
        role = field(analysis, "analysis", False)
    elif folder_role:
        role = field(folder_role, "folder", False)

    day = field(None, None, False)
    if shot_confirmed and shot_card and shot_card.shoot_day is not None:
        day = field(normalize_shoot_day(shot_card.shoot_day), "shot_card", True)
    elif media_confirmed and media_card and media_card.shoot_day is not None:
        day = field(normalize_shoot_day(media_card.shoot_day), "media_card", True)
    elif item is not None and item.shoot_day is not None and media_confirmed:
        day = field(normalize_shoot_day(item.shoot_day), "media_card", True)
    elif folder_day is not None:
        day = field(folder_day, "folder", False)
    elif item is not None and item.shoot_day is not None:
        day = field(normalize_shoot_day(item.shoot_day), "folder" if folder_day is not None else None, False)

    subjects: list[str] = []
    subjects_source = None
    subjects_confirmed = False
    if shot_confirmed and shot_card and shot_card.subjects:
        subjects = list(shot_card.subjects)
        subjects_source = "shot_card"
        subjects_confirmed = True
    elif media_confirmed and media_card and media_card.subjects:
        subjects = list(media_card.subjects)
        subjects_source = "media_card"
        subjects_confirmed = True

    note = ""
    note_source = None
    note_confirmed = False
    if shot_confirmed and shot_card and shot_card.note:
        note = shot_card.note
        note_source = "shot_card"
        note_confirmed = True
    elif media_confirmed and media_card and media_card.note:
        note = media_card.note
        note_source = "media_card"
        note_confirmed = True

    understand = understand_card_for_shot(shot, understand_cards) if shot is not None else None
    proposal = None
    if item is not None:
        proposal = propose_card(
            item,
            understand_cards=understand_cards,
            shots=[shot] if shot is not None else None,
            peers=peers,
        )
    conflicts = conflict_reasons(
        item,
        shot,
        shot_card=shot_card,
        resolved_role=role.get("value"),
        peers=peers,
    )
    needs = False
    if item is not None and item.kind != "audio":
        if shot is None:
            needs = bool(proposal and proposal.get("needs_confirmation") and not media_confirmed)
        else:
            shot_needs = bool(understand and understand.get("needs_confirmation"))
            needs = (not shot_confirmed) and (shot_needs or (not media_confirmed and role.get("value") is None))
            if not shot_confirmed and not media_confirmed and (analysis or folder_role):
                needs = True
        if conflicts:
            needs = True

    return {
        "media_id": media_id,
        "shot_id": shot_id,
        "role": role,
        "shoot_day": day,
        "subjects": field(subjects, subjects_source, subjects_confirmed),
        "note": field(note, note_source, note_confirmed),
        "needs_confirmation": needs,
        "conflicts": conflicts,
        "confirmed": bool((shot_confirmed and shot is not None) or (media_confirmed and shot is None)),
    }


def conflict_reasons(
    item: MediaItem | None,
    shot=None,
    *,
    shot_card: ShotCard | None = None,
    resolved_role: str | None = None,
    peers: list | None = None,
) -> list[str]:
    out: list[str] = []
    media_role = None
    if item is not None and is_carded(item) and item.card is not None and item.card.role:
        media_role = normalize_process_role(item.card.role)
    shot_role = normalize_process_role(shot_card.role) if shot_card and shot_card.confirmed else None
    if media_role and shot_role and not roles_equal(media_role, shot_role):
        out.append(f"shot role {shot_role} overrides media card {media_role}")
    role = resolved_role or shot_role or media_role
    captured = item.captured_at if item is not None else None
    if capture_contradicts_role(proposed_role=role, captured_at=captured, peers=peers or []):
        out.append("capture time contradicts role")
    return out


def confirmed_shot_roles_map(cards: dict[str, ShotCard] | list[ShotCard]) -> dict[str, str | None]:
    values = cards.values() if isinstance(cards, dict) else cards
    out: dict[str, str | None] = {}
    for card in values:
        if card.confirmed and card.role:
            out[card.shot_id] = normalize_process_role(card.role)
    return out


def is_unlabeled(resolved: dict, *, media_confirmed: bool, shot_confirmed: bool, scope: str) -> bool:
    if scope == "shot":
        return not shot_confirmed and not media_confirmed
    return not media_confirmed and not shot_confirmed


def matches_filter(resolved: dict, filt: str, *, media_confirmed: bool, shot_confirmed: bool, scope: str) -> bool:
    if filt not in QUEUE_FILTERS:
        return True
    if filt == "all":
        return True
    if filt == "conflicts":
        return bool(resolved.get("conflicts"))
    if filt == "needs_confirmation":
        return bool(resolved.get("needs_confirmation") or resolved.get("conflicts"))
    if filt == "unlabeled":
        return is_unlabeled(resolved, media_confirmed=media_confirmed, shot_confirmed=shot_confirmed, scope=scope)
    return True


def queue_item(
    item: MediaItem,
    shot,
    resolved: dict,
    *,
    scope: str,
) -> dict:
    filename = ""
    if item.original_path:
        filename = item.original_path.replace("\\", "/").split("/")[-1]
    elif item.path:
        filename = item.path.replace("\\", "/").split("/")[-1]
    return {
        "scope": scope,
        "media_id": item.id,
        "shot_id": resolved.get("shot_id"),
        "kind": item.kind,
        "filename": filename,
        "duration_s": float(_shot_attr(shot, "duration_s", item.duration_s) or 0.0),
        "in_s": _shot_attr(shot, "in_s"),
        "out_s": _shot_attr(shot, "out_s"),
        "keyframe": _shot_attr(shot, "keyframe"),
        "proxy_path": item.proxy_path or item.path,
        "captured_at": item.captured_at,
        "shoot_day": resolved.get("shoot_day", {}).get("value"),
        "labels": resolved,
        "needs_confirmation": resolved.get("needs_confirmation"),
        "conflicts": list(resolved.get("conflicts") or []),
        "carded": is_carded(item),
    }


def build_label_queue(
    media: list[MediaItem],
    *,
    shots_by_media: dict[str, list],
    shot_cards: dict[str, ShotCard],
    understand_by_media: dict[str, list],
    filt: str = "all",
    shoot_day=None,
    role: str | None = None,
) -> dict:
    groups: list[dict] = []
    items: list[dict] = []
    counts = {name: 0 for name in QUEUE_FILTERS}
    peers = list(media)
    for item in media:
        if item.kind == "audio":
            continue
        if shoot_day is not None and not shoot_days_equal(item.shoot_day, shoot_day):
            if item.card is None or not shoot_days_equal(item.card.shoot_day, shoot_day):
                continue
        shots = list(shots_by_media.get(item.id) or [])
        understand = list(understand_by_media.get(item.id) or [])
        any_shot_confirmed = any(
            shot_cards.get(str(_shot_attr(shot, "id") or ""), None) is not None
            and shot_cards[str(_shot_attr(shot, "id"))].confirmed
            for shot in shots
        )
        media_resolved = resolve_labels(
            item, None, understand_cards=understand, peers=peers
        )
        if role is not None and not roles_equal(media_resolved["role"]["value"], role):
            shot_hit = False
            for shot in shots:
                card = shot_cards.get(str(_shot_attr(shot, "id") or ""))
                resolved = resolve_labels(
                    item, shot, shot_card=card, understand_cards=understand, peers=peers
                )
                if roles_equal(resolved["role"]["value"], role):
                    shot_hit = True
                    break
            if not shot_hit:
                continue
        media_row = queue_item(item, None, media_resolved, scope="media")
        shot_rows: list[dict] = []
        for shot in shots:
            sid = str(_shot_attr(shot, "id") or "")
            card = shot_cards.get(sid)
            resolved = resolve_labels(
                item, shot, shot_card=card, understand_cards=understand, peers=peers
            )
            row = queue_item(item, shot, resolved, scope="shot")
            shot_rows.append(row)
            shot_confirmed = bool(card and card.confirmed)
            for name in QUEUE_FILTERS:
                if matches_filter(
                    resolved,
                    name,
                    media_confirmed=is_carded(item),
                    shot_confirmed=shot_confirmed,
                    scope="shot",
                ):
                    counts[name] += 1
            if matches_filter(
                resolved,
                filt,
                media_confirmed=is_carded(item),
                shot_confirmed=shot_confirmed,
                scope="shot",
            ):
                items.append(row)
        for name in QUEUE_FILTERS:
            if matches_filter(
                media_resolved,
                name,
                media_confirmed=is_carded(item),
                shot_confirmed=any_shot_confirmed,
                scope="media",
            ):
                counts[name] += 1
        if matches_filter(
            media_resolved,
            filt,
            media_confirmed=is_carded(item),
            shot_confirmed=any_shot_confirmed,
            scope="media",
        ):
            items.append(media_row)
            groups.append(
                {
                    "media_id": item.id,
                    "shoot_day": media_resolved["shoot_day"]["value"],
                    "filename": media_row["filename"],
                    "media": media_row,
                    "shots": [
                        row
                        for row in shot_rows
                        if matches_filter(
                            row["labels"],
                            filt,
                            media_confirmed=is_carded(item),
                            shot_confirmed=bool(
                                shot_cards.get(row["shot_id"] or "")
                                and shot_cards[row["shot_id"]].confirmed
                            ),
                            scope="shot",
                        )
                    ],
                }
            )
        elif any(
            matches_filter(
                row["labels"],
                filt,
                media_confirmed=is_carded(item),
                shot_confirmed=bool(
                    shot_cards.get(row["shot_id"] or "") and shot_cards[row["shot_id"]].confirmed
                ),
                scope="shot",
            )
            for row in shot_rows
        ):
            groups.append(
                {
                    "media_id": item.id,
                    "shoot_day": media_resolved["shoot_day"]["value"],
                    "filename": media_row["filename"],
                    "media": media_row,
                    "shots": [
                        row
                        for row in shot_rows
                        if matches_filter(
                            row["labels"],
                            filt,
                            media_confirmed=is_carded(item),
                            shot_confirmed=bool(
                                shot_cards.get(row["shot_id"] or "")
                                and shot_cards[row["shot_id"]].confirmed
                            ),
                            scope="shot",
                        )
                    ],
                }
            )
    return {"groups": groups, "items": items, "counts": counts, "filter": filt}


def collect_conflicts(
    media: list[MediaItem],
    *,
    shots_by_media: dict[str, list],
    shot_cards: dict[str, ShotCard],
    understand_by_media: dict[str, list],
) -> list[dict]:
    queued = build_label_queue(
        media,
        shots_by_media=shots_by_media,
        shot_cards=shot_cards,
        understand_by_media=understand_by_media,
        filt="conflicts",
    )
    return [row for row in queued["items"] if row.get("conflicts")]


def readiness_payload(
    media: list[MediaItem],
    *,
    shots_by_media: dict[str, list],
    shot_cards: dict[str, ShotCard],
    understand_by_media: dict[str, list],
) -> dict:
    queued = build_label_queue(
        media,
        shots_by_media=shots_by_media,
        shot_cards=shot_cards,
        understand_by_media=understand_by_media,
        filt="all",
    )
    visual = [item for item in media if item.kind != "audio"]
    carded = sum(1 for item in visual if is_carded(item))
    unlabeled = queued["counts"]["unlabeled"]
    needs = queued["counts"]["needs_confirmation"]
    conflicts = queued["counts"]["conflicts"]
    overrides = sum(1 for card in shot_cards.values() if card.confirmed)
    reasons: list[str] = []
    if not visual:
        reasons.append("no visual media")
    if needs:
        reasons.append(f"{needs} item(s) need confirmation")
    if conflicts:
        reasons.append(f"{conflicts} conflict(s)")
    bookend_uncarded = [
        item.id
        for item in visual
        if normalize_process_role(item.role) in ARC_BOOKEND_ROLES and not is_carded(item)
    ]
    if bookend_uncarded:
        reasons.append(f"{len(bookend_uncarded)} uncarded bookend(s)")
    ready = bool(visual) and not needs and not conflicts and not bookend_uncarded
    return {
        "ready": ready,
        "carded": carded,
        "total": len(visual),
        "unlabeled": unlabeled,
        "needs_confirmation": needs,
        "conflicts": conflicts,
        "shot_overrides": overrides,
        "reasons": reasons,
    }


__all__ = [
    "GUI_DOMAIN_TOOLS",
    "LABEL_UNDO_MAX",
    "analysis_role",
    "build_label_queue",
    "collect_conflicts",
    "confirmed_shot_roles_map",
    "field",
    "folder_hints",
    "readiness_payload",
    "resolve_labels",
    "understand_card_for_shot",
]
