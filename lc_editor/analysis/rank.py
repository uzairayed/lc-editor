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

UNDERSTAND_TAG_PREFIX = "understand:"
# Train C: strong preference so Director picks understand spans over bare index.
UNDERSTAND_BOOST = 0.45
UNDERSTAND_ANY_BOOST = 0.08

# Narrative roles (travel / reel sections) plus process / album roles for story lock.
NARRATIVE_ROLES = ("hook", "journey", "site_wide", "site_detail", "closer")
PROCESS_ROLES = (
    "before",
    "wash",
    "detail",
    "after",
    "hero",
    "skip_face",
    "engine",
    "wheel",
    "interior",
    "machine",
)
ROLES = NARRATIVE_ROLES + PROCESS_ROLES
SORTS = ("in_s", "motion", "duration_s")

# Process story order for Director / understand_timeline beat lists.
PROCESS_STORY_ORDER = (
    "before",
    "wash",
    "engine",
    "machine",
    "wheel",
    "interior",
    "detail",
    "after",
    "hero",
    "skip_face",
)

# Roles that prefer media tagged with the same name when any are tagged.
TAG_FILTER_ROLES = frozenset(
    {"before", "wash", "after", "machine", "detail", "wheel", "interior", "engine", "hero", "skip_face"}
)

# Legacy aliases kept for callers that still resolve onto narrative names.
ROLE_SCORE_ALIAS = {
    "detail": "site_detail",
    "hero": "hook",
    "before": "site_detail",
    "wash": "site_detail",
    "after": "site_detail",
    "machine": "site_detail",
    "wheel": "site_detail",
    "interior": "site_detail",
    "engine": "journey",
    "skip_face": "site_wide",
    "polish": "after",
}


def understand_tags_for_role(role: str) -> list[str]:
    role = (role or "").strip().lower()
    if not role:
        return []
    tags = [f"{UNDERSTAND_TAG_PREFIX}{role}"]
    if role == "after":
        tags.append(f"{UNDERSTAND_TAG_PREFIX}polish")
    elif role == "polish":
        tags.append(f"{UNDERSTAND_TAG_PREFIX}after")
    return tags


def shot_has_understand_role(shot: Shot, role: str) -> bool:
    wanted = set(understand_tags_for_role(role))
    return bool(wanted.intersection(shot.tags or []))


def shot_has_any_understand_tag(shot: Shot) -> bool:
    return any(str(t).startswith(UNDERSTAND_TAG_PREFIX) for t in (shot.tags or []))


def understand_boost(shot: Shot, role: str) -> float:
    """Prefer spans stamped by media_understand (same role ≫ any understand tag)."""
    if shot_has_understand_role(shot, role):
        return UNDERSTAND_BOOST
    if shot_has_any_understand_tag(shot):
        return UNDERSTAND_ANY_BOOST
    return 0.0


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


def resolve_score_role(role: str) -> str:
    return ROLE_SCORE_ALIAS.get(role, role)


def pool_for_role(
    shots: list[Shot],
    role: str,
    *,
    media_roles: dict[str, str | None] | None = None,
    confirmed_roles: dict[str, str | None] | None = None,
) -> list[Shot]:
    """Confirmed card > understand-tagged spans > media role tags > full pool."""
    if confirmed_roles:
        confirmed = [
            shot
            for shot in shots
            if roles_equal(confirmed_roles.get(shot.media_id), role)
        ]
        if confirmed:
            return confirmed
    understand_pool = [shot for shot in shots if shot_has_understand_role(shot, role)]
    if understand_pool:
        return understand_pool
    if role not in TAG_FILTER_ROLES or not media_roles:
        return list(shots)
    tagged = [
        shot
        for shot in shots
        if roles_equal(media_roles.get(shot.media_id), role)
    ]
    return tagged if tagged else list(shots)


def _audio_motion_bonus(metrics, *, engine_weight: float = 0.35, ambient_weight: float = 0.1) -> float:
    if metrics.audio_class == "engine":
        return engine_weight
    if metrics.audio_class == "ambient":
        return ambient_weight
    if metrics.audio_class == "speech":
        return 0.05
    return 0.0


def score_shot(
    shot: Shot,
    role: str,
    *,
    first_media_id: str | None = None,
    sizes: dict[str, tuple[int, int]] | None = None,
) -> float:
    """Score a shot for a narrative or process role (Train C/F process heuristics)."""
    metrics = shot.metrics
    role = (role or "").strip().lower()
    mapped = ROLE_SCORE_ALIAS.get(role, role)

    # Process / album roles: distinct heuristics so understand can label cleanly.
    # Train F: reduce wash/skip_face/hero monopoly on silent detailing; surface
    # before/after/interior/wheel when motion + luma/sharpness cues fit.
    if role == "before":
        # Dusty / dull: stable frame, usable sharpness, prefer lower luma (not polished).
        score = (
            0.35 * metrics.sharpness
            + 0.3 * (1.0 - metrics.motion)
            + 0.35 * (1.0 - metrics.luma_mean)
        )
        if metrics.luma_mean <= 0.4:
            score += 0.1
        if metrics.motion >= 0.35:
            score -= 0.15
    elif role == "wash":
        # Wet-work foam/scrub: real motion + texture spread. Silent ambient OK.
        # Do not steal sharp tool work (machine) or engine-audio bays.
        score = (
            0.45 * metrics.motion
            + 0.15 * metrics.sharpness
            + 0.2 * metrics.luma_spread
            + _audio_motion_bonus(metrics, engine_weight=0.05, ambient_weight=0.18)
        )
        if metrics.motion < 0.35:
            score -= 0.2
        if metrics.motion >= 0.55 and metrics.luma_spread >= 0.45:
            score += 0.1
        if metrics.sharpness >= 0.7 and metrics.motion < 0.6:
            score -= 0.12
        if metrics.audio_class == "engine":
            score -= 0.15
    elif role == "after" or role == "polish":
        # Clean / shiny payoff: sharp, bright, calm.
        score = (
            0.4 * metrics.sharpness
            + 0.35 * metrics.luma_mean
            + 0.25 * (1.0 - metrics.motion)
        )
        if metrics.luma_mean >= 0.55:
            score += 0.15
        if metrics.luma_mean >= 0.7 and metrics.sharpness >= 0.7 and metrics.motion < 0.25:
            score += 0.12
        if metrics.motion >= 0.35:
            score -= 0.15
    elif role == "machine":
        # Polisher / tool at work: motion + edge detail + ambient/engine audio.
        score = (
            0.35 * metrics.motion
            + 0.4 * metrics.sharpness
            + 0.15 * (1.0 - metrics.blur)
            + _audio_motion_bonus(metrics, engine_weight=0.2, ambient_weight=0.12)
        )
        if metrics.motion >= 0.35 and metrics.sharpness >= 0.55:
            score += 0.12
        if metrics.luma_spread >= 0.5 and metrics.sharpness < 0.55:
            score -= 0.08  # foamy wet-work leans wash
    elif role == "wheel":
        score = (
            0.55 * metrics.sharpness
            + 0.25 * (1.0 - metrics.motion)
            + 0.2 * (1.0 - metrics.blur)
        )
        if metrics.motion < 0.25 and metrics.sharpness >= 0.65:
            score += 0.1
        # Wheels usually have more local contrast than a flat cabin.
        if 0.28 <= metrics.luma_spread <= 0.55 and metrics.sharpness >= 0.7:
            score += 0.06
        if metrics.luma_mean >= 0.7:
            score -= 0.14  # bright shiny payoff leans after, not wheel
    elif role == "interior":
        # Cabin still: sharp + flatter luma (low spread) + often dimmer.
        score = (
            0.45 * metrics.sharpness
            + 0.2 * (1.0 - metrics.motion)
            + 0.15 * (1.0 - metrics.blur)
            + 0.2 * (1.0 - metrics.luma_spread)
        )
        if metrics.luma_spread <= 0.3 and metrics.sharpness >= 0.55:
            score += 0.12
        elif metrics.luma_spread > 0.4:
            score -= 0.1
        if metrics.luma_mean <= 0.45:
            score += 0.05
        if metrics.motion >= 0.3:
            score -= 0.12
        if metrics.luma_mean >= 0.7:
            score -= 0.12
    elif role == "engine":
        score = 0.55 * metrics.motion + _audio_motion_bonus(
            metrics, engine_weight=0.55, ambient_weight=0.02
        )
        if metrics.audio_class == "engine":
            score += 0.1
        else:
            score -= 0.12
    elif role == "hero":
        energy = 1.0 - abs(metrics.luma_mean - 0.5) * 2.0
        score = 0.45 * metrics.sharpness + 0.3 * max(0.0, energy) + 0.15 * metrics.luma_spread
        # Hero is a still presentational beat, not scrubbing / tool motion.
        if metrics.motion >= 0.3:
            score -= 0.25
        if first_media_id and shot.media_id == first_media_id and metrics.motion > 0.5:
            score -= 0.4
    elif role == "skip_face":
        # Calm wide only: high spread, low motion. Sharp detail stills are not skip.
        score = (
            0.35 * (1.0 - metrics.motion)
            + 0.45 * metrics.luma_spread
            + 0.1 * (1.0 - metrics.blur)
            + 0.1 * (1.0 - metrics.sharpness)
        )
        if metrics.luma_spread < 0.5:
            score -= 0.18
        if metrics.sharpness >= 0.65:
            score -= 0.15
    elif role == "detail":
        score = 0.7 * metrics.sharpness + 0.3 * (1.0 - metrics.motion)
    elif mapped == "hook" or role == "hook":
        energy = 1.0 - abs(metrics.luma_mean - 0.5) * 2.0
        score = 0.5 * metrics.sharpness + 0.3 * max(0.0, energy) + 0.2 * metrics.luma_spread
        if first_media_id and shot.media_id == first_media_id and metrics.motion > 0.5:
            score -= 0.4
    elif mapped == "journey" or role == "journey":
        bonus = 0.3 if metrics.audio_class == "engine" else 0.0
        score = 0.7 * metrics.motion + bonus
    elif mapped == "site_wide" or role == "site_wide":
        score = 0.6 * (1.0 - metrics.motion) + 0.4 * metrics.luma_spread
    elif mapped == "site_detail" or role == "site_detail":
        score = 0.7 * metrics.sharpness + 0.3 * (1.0 - metrics.motion)
    elif mapped == "closer" or role == "closer":
        duration_norm = min(1.0, shot.duration_s / SHOT_MAX_S)
        score = 0.5 * (1.0 - metrics.motion) + 0.5 * duration_norm
    else:
        raise ValueError(role)
    width, height = _size_of(shot, sizes)
    return score + resolution_boost(width, height) + understand_boost(shot, role)


def rank_shots(
    shots: list[Shot],
    role: str,
    top_k: int,
    *,
    first_media_id: str | None = None,
    sizes: dict[str, tuple[int, int]] | None = None,
    media_roles: dict[str, str | None] | None = None,
    shoot_days: dict[str, int | str | None] | None = None,
    confirmed_roles: dict[str, str | None] | None = None,
) -> list[Shot]:
    pool = pool_for_role(
        shots, role, media_roles=media_roles, confirmed_roles=confirmed_roles
    )

    def key(shot: Shot) -> tuple:
        width, height = _size_of(shot, sizes)
        return (
            -score_shot(shot, role, first_media_id=first_media_id, sizes=sizes),
            -short_side(width, height),
            shot.id,
        )

    ordered = prefer_hd_role_takes(
        sorted(pool, key=key),
        sizes=sizes,
        media_roles=media_roles,
        shoot_days=shoot_days,
    )
    if top_k < 0:
        top_k = 0
    return ordered[:top_k]
