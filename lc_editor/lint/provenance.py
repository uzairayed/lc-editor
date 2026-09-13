"""SPEC-ANA-18 / SPEC-ANA-19 review warnings. Soft only; never block export."""

from __future__ import annotations

from lc_editor.analysis.provenance import (
    arc_order_issues,
    resolve_slot_role,
    uncarded_slot_issues,
    understand_role_from_tags,
)
from lc_editor.models import Clip, MediaItem, Timeline, clip_media_ids


def _overlap(in_s: float, out_s: float, clip: Clip) -> bool:
    return float(in_s) < float(clip.out_s) + 1e-6 and float(out_s) > float(clip.in_s) - 1e-6


def _understand_role_for_clip(clip: Clip, media_id: str, understand_spans: dict[str, list] | None) -> str | None:
    spans = (understand_spans or {}).get(media_id) or []
    for span in spans:
        if isinstance(span, dict):
            in_s = float(span.get("in_s", 0.0) or 0.0)
            out_s = float(span.get("out_s", 0.0) or 0.0)
            if not _overlap(in_s, out_s, clip):
                continue
            role = span.get("role_hint") or span.get("role")
            if role:
                return str(role)
            tags = span.get("tags") or []
            tagged = understand_role_from_tags(tags)
            if tagged:
                return tagged
        else:
            in_s = float(getattr(span, "in_s", 0.0) or 0.0)
            out_s = float(getattr(span, "out_s", 0.0) or 0.0)
            if not _overlap(in_s, out_s, clip):
                continue
            tagged = understand_role_from_tags(getattr(span, "tags", None))
            if tagged:
                return tagged
    # Fall back to any span on the media (whole-file cards).
    for span in spans:
        if isinstance(span, dict):
            role = span.get("role_hint") or span.get("role")
            if role:
                return str(role)
            tagged = understand_role_from_tags(span.get("tags") or [])
            if tagged:
                return tagged
        else:
            tagged = understand_role_from_tags(getattr(span, "tags", None))
            if tagged:
                return tagged
    return None


def clip_slots(
    timeline: Timeline,
    media: list[MediaItem] | None,
    understand_spans: dict[str, list] | None = None,
) -> list[dict]:
    by_id = {item.id: item for item in (media or [])}
    slots: list[dict] = []
    for clip in timeline.clips:
        for mid in clip_media_ids(clip):
            item = by_id.get(mid)
            card_role = None
            if item is not None and item.card is not None:
                card_role = item.card.role
            role = resolve_slot_role(
                media_role=item.role if item is not None else None,
                card_role=card_role,
                understand_role=_understand_role_for_clip(clip, mid, understand_spans),
            )
            slots.append(
                {
                    "clip_id": clip.id,
                    "media_id": mid,
                    "role": role,
                    "captured_at": item.captured_at if item is not None else None,
                }
            )
    return slots


def provenance_warnings(
    timeline: Timeline,
    media: list[MediaItem] | None = None,
    understand_spans: dict[str, list] | None = None,
) -> list[str]:
    if not timeline.clips or not media:
        return []
    by_id = {item.id: item for item in media}
    slots = clip_slots(timeline, media, understand_spans)
    warns = arc_order_issues(slots)
    warns.extend(uncarded_slot_issues(slots, by_id))
    return warns
