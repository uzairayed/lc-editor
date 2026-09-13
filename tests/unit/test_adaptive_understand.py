"""Train B adaptive selection + cost metrics + album shared budget."""

from __future__ import annotations

from pathlib import Path

from lc_editor.analysis.adaptive import (
    allocate_shared_budget,
    clamp_shared_budget,
    focus_select,
    planted_quality,
    query_wants_aks,
    select_adaptive_shots,
    understand_cost_metrics,
    uniform_select,
)
from lc_editor.analysis.embedder import embedder_status, optional_embedder, vision_extra_enabled
from lc_editor.analysis.manifest import Shot, ShotMetrics, write_manifest
from lc_editor.analysis.understand import DEFAULT_PROCESS_ROLES
from lc_editor.app import Editor
from tests.conftest import touch_media


def _shot(media_id: str, index: int, **overrides) -> Shot:
    metrics = overrides.pop("metrics", ShotMetrics())
    in_s = overrides.pop("in_s", float(index) * 2)
    out_s = overrides.pop("out_s", in_s + overrides.pop("length", 2.0))
    data = {
        "id": f"hash_{index:02d}",
        "media_id": media_id,
        "in_s": in_s,
        "out_s": out_s,
        "duration_s": round(out_s - in_s, 4),
        "keyframe": overrides.pop("keyframe", f"/tmp/hash_{index:02d}.jpg"),
        "metrics": metrics,
        "tags": overrides.pop("tags", []),
    }
    data.update(overrides)
    return Shot.model_validate(data)


def _synthetic_timeline(n: int = 80) -> tuple[list[Shot], set[str]]:
    """Long timeline with a planted high-value cluster in the middle third."""
    shots: list[Shot] = []
    valuable: set[str] = set()
    for i in range(n):
        # Quiet filler by default.
        motion = 0.05
        sharpness = 0.2
        audio = "silent"
        # Plant interesting wash/machine cluster around indices 30–44.
        if 30 <= i <= 44:
            motion = 0.85
            sharpness = 0.55
            audio = "engine"
            valuable.add(f"hash_{i:02d}")
        # A sharp detail island later.
        if 60 <= i <= 64:
            motion = 0.08
            sharpness = 0.95
            audio = "ambient"
            valuable.add(f"hash_{i:02d}")
        shots.append(
            _shot(
                "syn",
                i,
                metrics=ShotMetrics(motion=motion, sharpness=sharpness, blur=1.0 - sharpness, audio_class=audio),
                length=2.0,
            )
        )
    return shots, valuable


def test_query_wants_aks_only_for_concrete_queries() -> None:
    assert query_wants_aks(None) is False
    assert query_wants_aks("process") is False
    assert query_wants_aks("album") is False
    assert query_wants_aks("find the wash and wheel detail") is True
    assert query_wants_aks("wash") is True


def test_focus_select_respects_budget_and_prefers_peaks() -> None:
    shots, valuable = _synthetic_timeline(80)
    picked = focus_select(shots, budget=16)
    assert len(picked) == 16
    quality = planted_quality(picked, valuable)
    uniform = uniform_select(shots, budget=16)
    uniform_q = planted_quality(uniform, valuable)
    # Adaptive should recover at least as many planted peaks as uniform.
    assert quality >= uniform_q
    assert quality >= 0.35


def test_aks_select_with_query_beats_uniform_on_planted() -> None:
    shots, valuable = _synthetic_timeline(80)
    adaptive = select_adaptive_shots(
        shots,
        12,
        query="wash machine detail",
        roles=list(DEFAULT_PROCESS_ROLES),
        selection="adaptive",
    )
    uniform = select_adaptive_shots(shots, 12, selection="uniform")
    assert len(adaptive) == 12
    assert len(uniform) == 12
    assert planted_quality(adaptive, valuable) >= planted_quality(uniform, valuable)


def test_cost_metrics_far_below_uniform() -> None:
    metrics = understand_cost_metrics(16, duration_s=160.0, selection="adaptive")
    assert metrics["frames_scored"] == 16
    assert metrics["duration_s"] == 160.0
    assert metrics["uniform_1fps_frames"] == 160
    assert metrics["frames_per_s"] == 0.1
    assert metrics["cost_ratio_vs_uniform"] == 0.1
    assert metrics["cost_ratio_vs_uniform"] < 0.25


def test_allocate_shared_budget_proportional() -> None:
    shares = allocate_shared_budget([10.0, 30.0, 60.0], total_budget=40, min_each=2)
    assert sum(shares) == 40
    assert shares[2] > shares[1] > shares[0]
    assert clamp_shared_budget(3) == 8
    assert clamp_shared_budget(999) == 256


def test_optional_embedder_off_by_default(monkeypatch) -> None:
    monkeypatch.delenv("LC_EDITOR_VISION", raising=False)
    assert vision_extra_enabled() is False
    assert optional_embedder() is None
    status = embedder_status()
    assert status["enabled"] is False
    assert status["active"] is False


def test_media_understand_exposes_adaptive_metrics(editor: Editor, tmp_path: Path) -> None:
    media = touch_media(tmp_path / "src", "adapt")
    editor.import_file(str(media))
    mid = editor.media[0].id
    shots, _valuable = _synthetic_timeline(60)
    for i, shot in enumerate(shots):
        kf = editor.store.keyframes_dir / f"a{i}.jpg"
        kf.write_bytes(b"\xff\xd8\xff\xd9")
        shots[i] = shot.model_copy(update={"media_id": mid, "keyframe": str(kf)})
    write_manifest(editor._manifest_for(editor.media[0]), shots)

    result = editor.media_understand(budget_frames=16, selection="adaptive")
    assert result["ok"] is True
    assert result["selection"] == "adaptive"
    assert result["shared_budget"] is False
    assert result["frames_scored"] == 16
    metrics = result["metrics"]
    assert metrics["frames_scored"] == 16
    assert metrics["duration_s"] >= 100.0
    assert metrics["cost_ratio_vs_uniform"] < 0.25
    assert metrics["frames_per_s"] < 0.25
    assert "embedder" in result
    assert result["embedder"]["active"] is False


def test_media_understand_shared_budget_album(editor: Editor, tmp_path: Path) -> None:
    a = touch_media(tmp_path / "src", "album_a")
    b = touch_media(tmp_path / "src", "album_b")
    editor.import_file(str(a))
    editor.import_file(str(b))
    assert len(editor.media) >= 2

    for idx, item in enumerate(editor.media[:2]):
        shots = []
        count = 40 if idx == 0 else 20
        for i in range(count):
            kf = editor.store.keyframes_dir / f"alb{idx}_{i}.jpg"
            kf.write_bytes(b"\xff\xd8\xff\xd9")
            shots.append(
                _shot(
                    item.id,
                    i,
                    metrics=ShotMetrics(motion=(i % 7) / 7, sharpness=0.5),
                    keyframe=str(kf),
                    length=2.0,
                )
            )
        write_manifest(editor._manifest_for(item), shots)

    result = editor.media_understand(budget_frames=24, shared_budget=True, selection="adaptive")
    assert result["ok"] is True
    assert result["shared_budget"] is True
    assert result["budget_frames"] == 24
    # Shared pool: total frames scored ≤ shared budget (not 24 * n media).
    assert result["frames_scored"] <= 24
    assert result["frames_scored"] >= 8
    media_ids = {s["media_id"] for s in result["spans"]}
    assert len(media_ids) >= 2
    assert result["metrics"]["shared_budget"] is True


def test_benchmark_adaptive_vs_uniform_quality_and_cost() -> None:
    """Lightweight fixture benchmark: better peak recall at same budget, cost << 1fps."""
    shots, valuable = _synthetic_timeline(100)
    budget = 20
    adaptive = select_adaptive_shots(shots, budget, selection="adaptive", roles=list(DEFAULT_PROCESS_ROLES))
    uniform = select_adaptive_shots(shots, budget, selection="uniform")
    legacy = select_adaptive_shots(shots, budget, selection="legacy")
    duration = max(s.out_s for s in shots) - min(s.in_s for s in shots)

    adaptive_q = planted_quality(adaptive, valuable)
    uniform_q = planted_quality(uniform, valuable)
    legacy_q = planted_quality(legacy, valuable)
    metrics = understand_cost_metrics(len(adaptive), duration, selection="adaptive")

    assert len(adaptive) == budget
    assert adaptive_q >= uniform_q
    assert adaptive_q >= 0.4
    # Legacy peaks should also beat pure uniform on this fixture, but adaptive is primary.
    assert max(adaptive_q, legacy_q) >= uniform_q
    assert metrics["cost_ratio_vs_uniform"] < 0.2
