from __future__ import annotations

import random

from lc_editor.analysis.shots import segment_shots
from lc_editor.models import SHOT_MAX_S, SHOT_MIN_S


def _assert_partition(spans: list[tuple[float, float]], duration_s: float) -> None:
    assert spans
    assert abs(spans[0][0] - 0.0) < 1e-6
    assert abs(spans[-1][1] - duration_s) < 1e-6
    for in_s, out_s in spans:
        assert out_s > in_s
    for prev, nxt in zip(spans, spans[1:]):
        assert abs(prev[1] - nxt[0]) < 1e-6


def test_no_events_one_shot_then_max_split() -> None:
    spans = segment_shots([], 5.0)
    _assert_partition(spans, 5.0)
    assert spans == [(0.0, 5.0)]

    long = segment_shots([], 20.0)
    _assert_partition(long, 20.0)
    assert all((out_s - in_s) <= SHOT_MAX_S + 1e-6 for in_s, out_s in long)
    assert len(long) == 3


def test_dense_events_merge_below_min() -> None:
    events = [0.1, 0.2, 0.3, 2.0]
    spans = segment_shots(events, 4.0)
    _assert_partition(spans, 4.0)
    assert all((out_s - in_s) >= SHOT_MIN_S - 1e-6 or len(spans) == 1 for in_s, out_s in spans)


def test_long_span_splits_evenly() -> None:
    spans = segment_shots([12.0], 24.0)
    _assert_partition(spans, 24.0)
    assert all((out_s - in_s) <= SHOT_MAX_S + 1e-6 for in_s, out_s in spans)


def test_events_at_zero_and_duration_ignored() -> None:
    spans = segment_shots([0.0, 2.0, 5.0], 5.0)
    _assert_partition(spans, 5.0)
    assert spans == [(0.0, 2.0), (2.0, 5.0)]


def test_float_jitter_is_stable() -> None:
    spans = segment_shots([1.9999999, 2.0000001, 4.0], 6.0)
    _assert_partition(spans, 6.0)
    assert spans[0] == (0.0, 2.0)


def test_video_shorter_than_min_is_one_shot() -> None:
    spans = segment_shots([0.1], 0.3)
    assert spans == [(0.0, 0.3)]


def test_randomized_events_keep_invariants() -> None:
    rng = random.Random(42)
    for _ in range(40):
        duration = rng.uniform(0.2, 30.0)
        n = rng.randint(0, 20)
        events = [rng.uniform(-0.5, duration + 0.5) for _ in range(n)]
        spans = segment_shots(events, duration)
        _assert_partition(spans, round(duration, 4))
        for in_s, out_s in spans:
            length = out_s - in_s
            if duration >= SHOT_MIN_S and len(spans) > 1:
                assert length >= SHOT_MIN_S - 1e-6
            assert length <= SHOT_MAX_S + 1e-6
