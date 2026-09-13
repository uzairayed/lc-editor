"""FOCUS / AKS-inspired adaptive frame selection (Train B).

Training-free. No required VLM weights. Scores indexed shots only under a
frame budget: coarse explore over temporal chunks, then fine exploit; when a
query is provided, balance relevance and temporal coverage (AKS-style).
"""

from __future__ import annotations

import math
from collections.abc import Callable
from dataclasses import dataclass

from lc_editor.analysis.manifest import Shot
from lc_editor.analysis.understand import (
    QUERY_PROCESS,
    best_role_hint,
    candidate_priority,
    coverage_indices,
)

RewardFn = Callable[[Shot], float]

DEFAULT_SELECTION = "adaptive"
SELECTION_MODES = frozenset({"adaptive", "uniform", "legacy"})
UNIFORM_BASELINE_FPS = 1.0
MAX_SHARED_BUDGET = 256
MIN_SHARED_BUDGET = 8


@dataclass(frozen=True)
class ChunkStats:
    index: int
    shots: tuple[Shot, ...]
    pulls: int
    mean: float
    m2: float  # sum of squared diffs for Welford variance

    @property
    def variance(self) -> float:
        if self.pulls < 2:
            return 0.0
        return self.m2 / (self.pulls - 1)

    def bernstein_radius(self, total_pulls: int) -> float:
        n = max(1, self.pulls)
        log_n = math.log(max(2, total_pulls))
        return math.sqrt(2.0 * self.variance * log_n / n) + (3.0 * log_n / n)

    def with_pull(self, reward: float) -> ChunkStats:
        pulls = self.pulls + 1
        delta = reward - self.mean
        mean = self.mean + delta / pulls
        m2 = self.m2 + delta * (reward - mean)
        return ChunkStats(self.index, self.shots, pulls, mean, m2)


def clamp_shared_budget(budget_frames: int | None, default: int = 64) -> int:
    if budget_frames is None:
        return default
    try:
        value = int(budget_frames)
    except (TypeError, ValueError):
        return default
    return max(MIN_SHARED_BUDGET, min(MAX_SHARED_BUDGET, value))


def normalize_selection(selection: str | None) -> str:
    name = (selection or DEFAULT_SELECTION).strip().lower()
    if name not in SELECTION_MODES:
        return DEFAULT_SELECTION
    return name


def query_wants_aks(query: str | None) -> bool:
    """True when the agent passed a concrete query (not blank process/album default)."""
    text = (query or "").strip().lower()
    if not text:
        return False
    return text not in QUERY_PROCESS


def _default_reward(shot: Shot) -> float:
    return candidate_priority(shot)


def partition_chunks(shots: list[Shot], n_chunks: int) -> list[list[Shot]]:
    ordered = sorted(shots, key=lambda s: (s.in_s, s.id))
    if not ordered:
        return []
    n_chunks = max(1, min(n_chunks, len(ordered)))
    chunks: list[list[Shot]] = [[] for _ in range(n_chunks)]
    for i, shot in enumerate(ordered):
        chunks[min(n_chunks - 1, (i * n_chunks) // len(ordered))].append(shot)
    return [c for c in chunks if c]


def focus_select(
    shots: list[Shot],
    budget: int,
    reward_fn: RewardFn | None = None,
    *,
    top_ratio: float = 0.4,
) -> list[Shot]:
    """Coarse → fine explore/exploit over temporal chunks (FOCUS-inspired)."""
    if not shots or budget <= 0:
        return []
    ordered = sorted(shots, key=lambda s: (s.in_s, s.id))
    if len(ordered) <= budget:
        return list(ordered)

    reward = reward_fn or _default_reward
    n_chunks = max(2, min(16, int(round(math.sqrt(len(ordered)) * 1.25))))
    raw_chunks = partition_chunks(ordered, n_chunks)
    if not raw_chunks:
        return uniform_select(ordered, budget)

    # Coarse: one exploratory pull per chunk (best local candidate).
    coarse_hits: list[tuple[int, Shot, float]] = []
    for index, chunk in enumerate(raw_chunks):
        probe = max(chunk, key=lambda s: (reward(s), -s.in_s, s.id))
        coarse_hits.append((index, probe, reward(probe)))

    total_pulls = max(1, len(coarse_hits))
    stats: list[ChunkStats] = []
    for index, chunk in enumerate(raw_chunks):
        probe_reward = next(r for i, _s, r in coarse_hits if i == index)
        stats.append(
            ChunkStats(index=index, shots=tuple(chunk), pulls=1, mean=probe_reward, m2=0.0)
        )

    # Rank chunks by optimistic bound (Bernstein UCB).
    def ucb(c: ChunkStats) -> float:
        return c.mean + c.bernstein_radius(total_pulls)

    ranked_chunks = sorted(stats, key=lambda c: (-ucb(c), -c.mean, c.index))
    m = max(1, min(len(ranked_chunks), int(math.ceil(len(ranked_chunks) * top_ratio))))
    # Always keep at least the empirical top half of means among finalists.
    by_mean = sorted(stats, key=lambda c: (-c.mean, c.index))
    top_ids = {c.index for c in ranked_chunks[:m]}
    top_ids.update(c.index for c in by_mean[: max(1, m // 2 + 1)])
    top_chunks = [raw_chunks[i] for i in sorted(top_ids)]

    picked: dict[str, Shot] = {}
    # Seed with coarse probes from top chunks so we never drop the evidence.
    for index, probe, _r in coarse_hits:
        if index in top_ids and len(picked) < budget:
            picked[probe.id] = probe

    # Fine: fill remaining budget from top chunks by reward (exploit).
    pool = [s for chunk in top_chunks for s in chunk if s.id not in picked]
    pool.sort(key=lambda s: (-reward(s), s.in_s, s.id))
    for shot in pool:
        if len(picked) >= budget:
            break
        picked[shot.id] = shot

    # If still short (tiny top set), spill into global leftovers by reward.
    if len(picked) < budget:
        leftover = [s for s in ordered if s.id not in picked]
        leftover.sort(key=lambda s: (-reward(s), s.in_s, s.id))
        for shot in leftover:
            if len(picked) >= budget:
                break
            picked[shot.id] = shot

    # Light coverage insurance: keep earliest / latest when budget allows swap.
    if ordered[0].id not in picked and len(picked) >= budget:
        weakest = min(picked.values(), key=lambda s: (reward(s), s.id))
        if reward(ordered[0]) + 1e-9 >= reward(weakest):
            del picked[weakest.id]
            picked[ordered[0].id] = ordered[0]
    if ordered[-1].id not in picked and len(picked) >= budget:
        weakest = min(picked.values(), key=lambda s: (reward(s), s.id))
        if weakest.id not in (ordered[0].id,) and reward(ordered[-1]) + 1e-9 >= reward(weakest):
            del picked[weakest.id]
            picked[ordered[-1].id] = ordered[-1]
    elif ordered[-1].id not in picked and len(picked) < budget:
        picked[ordered[-1].id] = ordered[-1]

    return sorted(picked.values(), key=lambda s: (s.in_s, s.id))[:budget]


def _coverage_gain(selected_times: list[float], candidate_t: float, duration: float, bins: int) -> float:
    if duration <= 0 or bins <= 0:
        return 0.0
    width = duration / bins
    if width <= 0:
        return 0.0

    def bin_of(t: float) -> int:
        return min(bins - 1, max(0, int(t / width)))

    occupied = {bin_of(t) for t in selected_times}
    b = bin_of(candidate_t)
    if b not in occupied:
        return 1.0
    # Soft gain: prefer emptier neighborhoods.
    neighbors = {b - 1, b, b + 1}
    filled = sum(1 for n in neighbors if 0 <= n < bins and n in occupied)
    return max(0.0, 1.0 - filled / 3.0)


def aks_select(
    shots: list[Shot],
    budget: int,
    relevance_fn: RewardFn,
    *,
    alpha: float = 0.65,
) -> list[Shot]:
    """Greedy relevance + temporal coverage (AKS-inspired)."""
    if not shots or budget <= 0:
        return []
    ordered = sorted(shots, key=lambda s: (s.in_s, s.id))
    if len(ordered) <= budget:
        return list(ordered)

    duration = max(s.out_s for s in ordered) - min(s.in_s for s in ordered)
    if duration <= 0:
        duration = float(len(ordered))
    bins = max(4, min(budget * 2, 64))
    remaining = list(ordered)
    selected: list[Shot] = []
    selected_times: list[float] = []

    while remaining and len(selected) < budget:
        best: Shot | None = None
        best_score = float("-inf")
        for shot in remaining:
            mid = (shot.in_s + shot.out_s) / 2.0
            rel = relevance_fn(shot)
            cov = _coverage_gain(selected_times, mid, duration, bins)
            score = alpha * rel + (1.0 - alpha) * cov
            if score > best_score or (score == best_score and best is not None and shot.id < best.id):
                best_score = score
                best = shot
            elif best is None:
                best = shot
                best_score = score
        assert best is not None
        selected.append(best)
        selected_times.append((best.in_s + best.out_s) / 2.0)
        remaining = [s for s in remaining if s.id != best.id]

    return sorted(selected, key=lambda s: (s.in_s, s.id))


def uniform_select(shots: list[Shot], budget: int) -> list[Shot]:
    ordered = sorted(shots, key=lambda s: (s.in_s, s.id))
    if not ordered or budget <= 0:
        return []
    if len(ordered) <= budget:
        return list(ordered)
    return [ordered[i] for i in coverage_indices(len(ordered), budget)]


def relevance_for_query(
    shot: Shot,
    query: str,
    roles: list[str],
    *,
    first_media_id: str | None = None,
    sizes: dict[str, tuple[int, int]] | None = None,
    embedder_score: float | None = None,
) -> float:
    """Heuristic relevance in [0, ~2]; optional embedder score blends in when present."""
    text = (query or "").strip().lower()
    tokens = {p for p in text.replace(",", " ").split() if p}
    role, role_score = best_role_hint(shot, roles, first_media_id=first_media_id, sizes=sizes)
    # Prefer roles named in the query.
    token_hit = 1.0 if role in tokens or any(t in role for t in tokens) else 0.35
    for role_name in roles:
        if role_name in tokens:
            token_hit = max(token_hit, 0.55 + 0.45 * (1.0 if role_name == role else 0.0))
            break
    base = 0.55 * max(0.0, role_score) + 0.25 * candidate_priority(shot) + 0.2 * token_hit
    if embedder_score is None:
        return base
    # Soft blend; embedder already expected in ~[0, 1].
    return 0.45 * base + 0.55 * max(0.0, min(1.0, float(embedder_score)))


def select_adaptive_shots(
    shots: list[Shot],
    budget: int,
    *,
    query: str | None = None,
    roles: list[str] | None = None,
    selection: str | None = None,
    first_media_id: str | None = None,
    sizes: dict[str, tuple[int, int]] | None = None,
    embedder: Callable[[Shot, str], float | None] | None = None,
) -> list[Shot]:
    """Pick up to ``budget`` shots via adaptive / AKS / uniform / legacy."""
    from lc_editor.analysis.understand import select_candidate_shots

    mode = normalize_selection(selection)
    if not shots or budget <= 0:
        return []
    if mode == "uniform":
        return uniform_select(shots, budget)
    if mode == "legacy":
        return select_candidate_shots(shots, budget)

    role_list = list(roles or [])
    if query_wants_aks(query) and role_list:

        def _rel(shot: Shot) -> float:
            emb = None
            if embedder is not None and query:
                emb = embedder(shot, query)
            return relevance_for_query(
                shot,
                query or "",
                role_list,
                first_media_id=first_media_id,
                sizes=sizes,
                embedder_score=emb,
            )

        return aks_select(shots, budget, _rel)

    # FOCUS explore/exploit uses interestingness; role labels are applied later
    # when building span cards (Train A scorer), not during arm selection.
    return focus_select(shots, budget, _default_reward)


def allocate_shared_budget(
    durations_s: list[float],
    total_budget: int,
    *,
    min_each: int = 2,
) -> list[int]:
    """Split a shared frame budget across media proportional to duration."""
    n = len(durations_s)
    if n == 0:
        return []
    if total_budget <= 0:
        return [0] * n
    if n == 1:
        return [total_budget]

    floors = [min_each] * n
    floor_sum = floors[0] * n
    if floor_sum >= total_budget:
        # Spread as evenly as possible.
        base = total_budget // n
        rem = total_budget % n
        return [base + (1 if i < rem else 0) for i in range(n)]

    remaining = total_budget - floor_sum
    weights = [max(0.01, float(d)) for d in durations_s]
    weight_sum = sum(weights)
    raw = [remaining * (w / weight_sum) for w in weights]
    shares = [floor + int(math.floor(r)) for floor, r in zip(floors, raw, strict=True)]
    leftover = total_budget - sum(shares)
    order = sorted(range(n), key=lambda i: (-(raw[i] - math.floor(raw[i])), -weights[i], i))
    for i in order:
        if leftover <= 0:
            break
        shares[i] += 1
        leftover -= 1
    return shares


def media_duration_s(shots: list[Shot]) -> float:
    if not shots:
        return 0.0
    return max(0.0, max(s.out_s for s in shots) - min(s.in_s for s in shots))


def understand_cost_metrics(
    frames_scored: int,
    duration_s: float,
    *,
    selection: str = DEFAULT_SELECTION,
    shared_budget: bool = False,
    uniform_fps: float = UNIFORM_BASELINE_FPS,
) -> dict:
    """Expose frames_scored / duration vs a uniform 1fps baseline."""
    dur = max(0.0, float(duration_s))
    scored = max(0, int(frames_scored))
    uniform_frames = int(math.ceil(dur * uniform_fps)) if dur > 0 else 0
    frames_per_s = (scored / dur) if dur > 0 else 0.0
    cost_ratio = (scored / uniform_frames) if uniform_frames > 0 else 0.0
    return {
        "frames_scored": scored,
        "duration_s": round(dur, 4),
        "frames_per_s": round(frames_per_s, 6),
        "uniform_1fps_frames": uniform_frames,
        "cost_ratio_vs_uniform": round(cost_ratio, 6),
        "selection": normalize_selection(selection),
        "shared_budget": bool(shared_budget),
    }


def planted_quality(
    selected: list[Shot],
    valuable_ids: set[str],
) -> float:
    """Fraction of planted high-value shots recovered (benchmark helper)."""
    if not valuable_ids:
        return 0.0
    hit = sum(1 for s in selected if s.id in valuable_ids)
    return hit / len(valuable_ids)


__all__ = [
    "DEFAULT_SELECTION",
    "MAX_SHARED_BUDGET",
    "MIN_SHARED_BUDGET",
    "SELECTION_MODES",
    "UNIFORM_BASELINE_FPS",
    "aks_select",
    "allocate_shared_budget",
    "clamp_shared_budget",
    "focus_select",
    "media_duration_s",
    "normalize_selection",
    "partition_chunks",
    "planted_quality",
    "query_wants_aks",
    "relevance_for_query",
    "select_adaptive_shots",
    "understand_cost_metrics",
    "uniform_select",
]
