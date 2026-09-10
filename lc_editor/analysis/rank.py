from __future__ import annotations

from lc_editor.analysis.manifest import Shot
from lc_editor.analysis.media import (
    is_sub_720,
    normalize_role,
    normalize_shoot_day,
    resolution_boost,
    roles_equal,
    shoot_days_equal,
    short_side,
)
from lc_editor.models import SHOT_MAX_S

ROLES = ("hook", "journey", "site_wide", "site_detail", "closer")
SORTS = ("in_s", "motion", "duration_s")


def contradictory_filters(
    min_duration_s: float | None,
    max_duration_s: float | None,
    min_motion: float | None,
    max_motion: float | None,
) -> str | None:
    if min_duration_s is not None and max_duration_s is not None and min_duration_s > max_duration_s:
        return "contradictory duration filters"
    if min_motion is not None and max_motion is not None and min_motion > max_motion:
        return "contradictory motion filters"
    return None


def filter_shots(
    shots: list[Shot],
    *,
    min_duration_s: float | None = None,
    max_duration_s: float | None = None,
    min_motion: float | None = None,
    max_motion: float | None = None,
    audio_class: str | None = None,
    kinds: dict[str, str] | None = None,
    kind: str | None = None,
) -> list[Shot]:
    out: list[Shot] = []
    for shot in shots:
        if min_duration_s is not None and shot.duration_s < min_duration_s:
            continue
        if max_duration_s is not None and shot.duration_s > max_duration_s:
            continue
        if min_motion is not None and shot.metrics.motion < min_motion:
            continue
        if max_motion is not None and shot.metrics.motion > max_motion:
            continue
        if audio_class is not None and shot.metrics.audio_class != audio_class:
            continue
        if kind is not None and kinds is not None and kinds.get(shot.media_id) != kind:
            continue
        out.append(shot)
    return out


def sort_shots(shots: list[Shot], sort: str | None, media_order: list[str]) -> list[Shot]:
    index = {media_id: i for i, media_id in enumerate(media_order)}

    def key(shot: Shot) -> tuple:
        capture = index.get(shot.media_id, len(index))
        if sort == "motion":
            return (shot.metrics.motion, shot.id)
        if sort == "duration_s":
            return (shot.duration_s, shot.id)
        if sort == "in_s":
            return (shot.in_s, capture, shot.id)
        return (capture, shot.in_s, shot.id)

    return sorted(shots, key=key)


def _size_of(shot: Shot, sizes: dict[str, tuple[int, int]] | None) -> tuple[int, int]:
    if not sizes:
        return (0, 0)
    return sizes.get(shot.media_id, (0, 0))


def _is_soft(shot: Shot, sizes: dict[str, tuple[int, int]] | None) -> bool:
    width, height = _size_of(shot, sizes)
    return is_sub_720(width, height)


def _same_role_hd_alternate(
    shot: Shot,
    other: Shot,
    *,
    sizes: dict[str, tuple[int, int]] | None,
    media_roles: dict[str, str | None] | None,
    shoot_days: dict[str, int | str | None] | None,
) -> bool:
    if not media_roles or _is_soft(other, sizes):
        return False
    if not roles_equal(media_roles.get(shot.media_id), media_roles.get(other.media_id)):
        return False
    if not shoot_days:
        return True
    left = normalize_shoot_day(shoot_days.get(shot.media_id))
    right = normalize_shoot_day(shoot_days.get(other.media_id))
    if left is not None and right is not None:
        return shoot_days_equal(left, right)
    return True


def prefer_hd_role_takes(
    shots: list[Shot],
    *,
    sizes: dict[str, tuple[int, int]] | None = None,
    media_roles: dict[str, str | None] | None = None,
    shoot_days: dict[str, int | str | None] | None = None,
) -> list[Shot]:
    """Promote an HD same-role sibling above a soft, role-tagged take."""
    if not shots or not media_roles:
        return list(shots)
    ordered = list(shots)
    i = 0
    while i < len(ordered):
        shot = ordered[i]
        if not _is_soft(shot, sizes) or not normalize_role(media_roles.get(shot.media_id)):
            i += 1
            continue
        alt_idx = next(
            (
                j
                for j, other in enumerate(ordered)
                if _same_role_hd_alternate(
                    shot, other, sizes=sizes, media_roles=media_roles, shoot_days=shoot_days
                )
            ),
            None,
        )
        if alt_idx is not None and alt_idx > i:
            ordered.insert(i, ordered.pop(alt_idx))
        i += 1
    return ordered


def score_shot(
    shot: Shot,
    role: str,
    *,
    first_media_id: str | None = None,
    sizes: dict[str, tuple[int, int]] | None = None,
) -> float:
    metrics = shot.metrics
    if role == "hook":
        energy = 1.0 - abs(metrics.luma_mean - 0.5) * 2.0
        score = 0.5 * metrics.sharpness + 0.3 * max(0.0, energy) + 0.2 * metrics.luma_spread
        if first_media_id and shot.media_id == first_media_id and metrics.motion > 0.5:
            score -= 0.4
    elif role == "journey":
        bonus = 0.3 if metrics.audio_class == "engine" else 0.0
        score = 0.7 * metrics.motion + bonus
    elif role == "site_wide":
        score = 0.6 * (1.0 - metrics.motion) + 0.4 * metrics.luma_spread
    elif role == "site_detail":
        score = 0.7 * metrics.sharpness + 0.3 * (1.0 - metrics.motion)
    elif role == "closer":
        duration_norm = min(1.0, shot.duration_s / SHOT_MAX_S)
        score = 0.5 * (1.0 - metrics.motion) + 0.5 * duration_norm
    else:
        raise ValueError(role)
    width, height = _size_of(shot, sizes)
    return score + resolution_boost(width, height)


def rank_shots(
    shots: list[Shot],
    role: str,
    top_k: int,
    *,
    first_media_id: str | None = None,
    sizes: dict[str, tuple[int, int]] | None = None,
    media_roles: dict[str, str | None] | None = None,
    shoot_days: dict[str, int | str | None] | None = None,
) -> list[Shot]:
    def key(shot: Shot) -> tuple:
        width, height = _size_of(shot, sizes)
        return (
            -score_shot(shot, role, first_media_id=first_media_id, sizes=sizes),
            -short_side(width, height),
            shot.id,
        )

    ordered = prefer_hd_role_takes(
        sorted(shots, key=key),
        sizes=sizes,
        media_roles=media_roles,
        shoot_days=shoot_days,
    )
    if top_k < 0:
        top_k = 0
    return ordered[:top_k]
