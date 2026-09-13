from __future__ import annotations

from pathlib import Path

from lc_editor.analysis.manifest import Shot, ShotMetrics, load_manifest, write_manifest
from lc_editor.analysis.rank import UNDERSTAND_BOOST, score_shot
from lc_editor.analysis.understand import (
    DEFAULT_BUDGET_FRAMES,
    MAX_BUDGET_FRAMES,
    apply_understand_tags,
    clamp_budget,
    refine_windows,
    resolve_understand_roles,
    select_candidate_shots,
)
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


def test_clamp_budget_and_default_roles() -> None:
    assert clamp_budget(None) == DEFAULT_BUDGET_FRAMES
    assert clamp_budget(3) == 8
    assert clamp_budget(99) == MAX_BUDGET_FRAMES
    assert resolve_understand_roles() == [
        "before",
        "wash",
        "wheel",
        "interior",
        "engine",
        "machine",
        "after",
        "hero",
        "skip_face",
    ]
    assert resolve_understand_roles(query="wash") == ["wash"]
    assert resolve_understand_roles(roles=["wheel", "interior"]) == ["wheel", "interior"]


def test_select_candidate_shots_respects_budget() -> None:
    shots = [
        _shot(
            "m1",
            i,
            metrics=ShotMetrics(motion=0.1 * (i % 5), sharpness=0.5, audio_class="ambient"),
            length=2.0,
        )
        for i in range(40)
    ]
    picked = select_candidate_shots(shots, budget=12)
    assert len(picked) == 12
    assert picked[0].id == shots[0].id or picked[0].in_s <= shots[1].in_s
    # Coverage should include early and late material.
    times = [s.in_s for s in picked]
    assert min(times) <= 4.0
    assert max(times) >= 60.0


def test_refine_windows_dense_inside_span() -> None:
    windows = refine_windows(10.0, 18.0, budget=8)
    assert 2 <= len(windows) <= 8
    assert windows[0][0] == 10.0
    assert windows[-1][1] == 18.0
    for a, b in windows:
        assert b > a


def test_media_understand_returns_process_spans(editor: Editor, tmp_path: Path) -> None:
    media = touch_media(tmp_path / "src", "detail_long")
    editor.import_file(str(media))
    mid = editor.media[0].id
    shots = [
        _shot(mid, 0, metrics=ShotMetrics(motion=0.8, sharpness=0.2, audio_class="engine"), length=4.0),
        _shot(mid, 1, metrics=ShotMetrics(motion=0.1, sharpness=0.9, blur=0.1), length=4.0),
        _shot(mid, 2, metrics=ShotMetrics(motion=0.2, sharpness=0.85, blur=0.1), length=4.0),
        _shot(mid, 3, metrics=ShotMetrics(motion=0.6, sharpness=0.4, audio_class="ambient"), length=4.0),
    ]
    for i, shot in enumerate(shots):
        kf = editor.store.keyframes_dir / f"u{i}.jpg"
        kf.parent.mkdir(parents=True, exist_ok=True)
        kf.write_bytes(b"\xff\xd8\xff" + b"\x00" * 80 + b"\xd9")
        shots[i] = shot.model_copy(update={"keyframe": str(kf)})
    write_manifest(editor._manifest_for(editor.media[0]), shots)

    version = editor.timeline_get()["timeline_summary"]["version"]
    result = editor.media_understand(budget_frames=32)
    assert result["ok"] is True
    assert result["timeline_summary"]["version"] == version
    assert result["budget_frames"] == 32
    assert result["frames_scored"] <= 32
    assert result["selection"] == "adaptive"
    assert "metrics" in result
    assert result["metrics"]["frames_scored"] == result["frames_scored"]
    assert result["spans"]
    card = result["spans"][0]
    for key in ("media_id", "in_s", "out_s", "role_hint", "score", "keyframe_path", "reason", "role_scores"):
        assert key in card
    assert card["role_hint"] in result["roles"]
    assert isinstance(card["role_scores"], dict)
    assert card["role_hint"] in card["role_scores"]
    assert Path(card["keyframe_path"]).exists()

    # Tags stamped into the index cache.
    stamped = load_manifest(editor._manifest_for(editor.media[0]))
    assert any(any(str(t).startswith("understand:") for t in (s.tags or [])) for s in stamped)
    assert editor._understand_for(editor.media[0]).exists()


def test_media_understand_budget_caps_long_index(editor: Editor, tmp_path: Path) -> None:
    media = touch_media(tmp_path / "src", "album")
    editor.import_file(str(media))
    mid = editor.media[0].id
    shots = []
    for i in range(80):
        kf = editor.store.keyframes_dir / f"long{i}.jpg"
        kf.write_bytes(b"\xff\xd8\xff\xd9")
        shots.append(
            _shot(
                mid,
                i,
                metrics=ShotMetrics(motion=(i % 10) / 10, sharpness=0.5),
                keyframe=str(kf),
                length=2.0,
            )
        )
    write_manifest(editor._manifest_for(editor.media[0]), shots)
    result = editor.media_understand(budget_frames=16)
    assert result["ok"] is True
    assert result["frames_scored"] == 16
    assert len(result["spans"]) == 16


def test_media_understand_refine_local_only(editor: Editor, tmp_path: Path) -> None:
    media = touch_media(tmp_path / "src", "refine")
    editor.import_file(str(media))
    mid = editor.media[0].id
    kf = editor.store.keyframes_dir / "base.jpg"
    kf.write_bytes(b"\xff\xd8\xff\xd9")
    shots = [
        _shot(mid, 0, metrics=ShotMetrics(motion=0.2, sharpness=0.5), keyframe=str(kf), length=8.0),
    ]
    write_manifest(editor._manifest_for(editor.media[0]), shots)
    before = len(editor.runner.calls)
    result = editor.media_understand_refine(mid, 1.0, 5.0, reason="uncertain wash", budget_frames=8)
    assert result["ok"] is True
    assert result["spans"]
    assert result["frames_scored"] <= 8
    assert all(1.0 - 1e-6 <= s["in_s"] and s["out_s"] <= 5.0 + 1e-6 for s in result["spans"])
    assert any("uncertain wash" in s["reason"] for s in result["spans"])
    # Only local keyframe extracts, not a full analysis pass.
    joined = " ".join(" ".join(c) for c in editor.runner.calls[before:])
    assert "scdet" not in joined


def test_shots_rank_prefers_understand_tagged(editor: Editor, tmp_path: Path) -> None:
    media = touch_media(tmp_path / "src", "rank")
    editor.import_file(str(media))
    mid = editor.media[0].id
    soft = _shot(mid, 0, metrics=ShotMetrics(motion=0.05, sharpness=0.7), length=3.0)
    sharp = _shot(
        mid,
        1,
        metrics=ShotMetrics(motion=0.05, sharpness=0.71),
        length=3.0,
        tags=["understand:wheel"],
    )
    write_manifest(editor._manifest_for(editor.media[0]), [soft, sharp])
    ranked = editor.shots_rank("wheel", top_k=2)
    assert ranked["ok"] is True
    assert ranked["shots"][0]["id"] == sharp.id
    assert score_shot(sharp, "wheel") >= score_shot(soft, "wheel") + UNDERSTAND_BOOST - 1e-9


def test_shots_search_matches_understand_tag(editor: Editor, tmp_path: Path) -> None:
    media = touch_media(tmp_path / "src", "search")
    editor.import_file(str(media))
    mid = editor.media[0].id
    shots = [
        _shot(mid, 0, metrics=ShotMetrics(motion=0.1, sharpness=0.8), length=3.0, tags=["understand:interior"]),
        _shot(mid, 1, metrics=ShotMetrics(motion=0.1, sharpness=0.8), length=3.0),
    ]
    write_manifest(editor._manifest_for(editor.media[0]), shots)
    found = editor.shots_search(role="interior")
    assert found["ok"] is True
    assert [s["id"] for s in found["shots"]] == [shots[0].id]


def test_apply_understand_tags_replaces_stale() -> None:
    shots = [
        _shot("m", 0, tags=["understand:wash", "keep"]),
        _shot("m", 1, tags=["other"]),
    ]
    cards = [
        {
            "shot_id": shots[0].id,
            "role_hint": "wheel",
            "media_id": "m",
            "in_s": 0,
            "out_s": 2,
            "score": 1,
            "keyframe_path": "x",
            "reason": "r",
        }
    ]
    updated = apply_understand_tags(shots, cards)
    assert "keep" in updated[0].tags
    assert "understand:wheel" in updated[0].tags
    assert "understand:wash" not in updated[0].tags
    assert updated[1].tags == ["other"]
