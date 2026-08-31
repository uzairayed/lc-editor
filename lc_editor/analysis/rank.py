from __future__ import annotations

from lc_editor.analysis.manifest import Shot
from lc_editor.models import SHOT_MAX_S

CANONICAL_ROLES = ("hook", "journey", "site_wide", "site_detail", "closer")
ROLE_ALIASES = {
    "motion": "journey",
    "body": "journey",
    "wide": "site_wide",
    "detail": "site_detail",
}
ROLES = CANONICAL_ROLES + tuple(ROLE_ALIASES)
SORTS = ("in_s", "motion", "duration_s")


def resolve_role(role: str) -> str | None:
    if role in CANONICAL_ROLES:
        return role
    return ROLE_ALIASES.get(role)


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


def score_shot(shot: Shot, role: str, *, first_media_id: str | None = None) -> float:
    metrics = shot.metrics
    resolved = resolve_role(role)
    if resolved == "hook":
        energy = 1.0 - abs(metrics.luma_mean - 0.5) * 2.0
        score = 0.5 * metrics.sharpness + 0.3 * max(0.0, energy) + 0.2 * metrics.luma_spread
        if first_media_id and shot.media_id == first_media_id and metrics.motion > 0.5:
            score -= 0.4
        return score
    if resolved == "journey":
        return 0.7 * metrics.motion
    if resolved == "site_wide":
        return 0.6 * (1.0 - metrics.motion) + 0.4 * metrics.luma_spread
    if resolved == "site_detail":
        return 0.7 * metrics.sharpness + 0.3 * (1.0 - metrics.motion)
    if resolved == "closer":
        duration_norm = min(1.0, shot.duration_s / SHOT_MAX_S)
        return 0.5 * (1.0 - metrics.motion) + 0.5 * duration_norm
    raise ValueError(role)


def rank_shots(
    shots: list[Shot],
    role: str,
    top_k: int,
    *,
    first_media_id: str | None = None,
) -> list[Shot]:
    resolved = resolve_role(role)
    if resolved is None:
        raise ValueError(role)
    ordered = sorted(
        shots,
        key=lambda shot: (-score_shot(shot, resolved, first_media_id=first_media_id), shot.id),
    )
    if top_k < 0:
        top_k = 0
    return ordered[:top_k]
