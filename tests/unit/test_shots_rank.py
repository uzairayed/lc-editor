from __future__ import annotations

from pathlib import Path

from lc_editor.analysis.manifest import Shot, ShotMetrics, write_manifest
from lc_editor.analysis.rank import rank_shots, score_shot
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
    }
    data.update(overrides)
    return Shot.model_validate(data)


def test_journey_prefers_highest_motion() -> None:
    shots = [
        _shot("m1", 0, metrics=ShotMetrics(motion=0.2, audio_class="engine")),
        _shot("m1", 1, metrics=ShotMetrics(motion=0.9, audio_class="ambient")),
        _shot("m1", 2, metrics=ShotMetrics(motion=0.4, audio_class="engine")),
    ]
    ranked = rank_shots(shots, "journey", 1)
    assert ranked[0].id == "hash_01"


def test_closer_prefers_calm_long_shot() -> None:
    shots = [
        _shot("m1", 0, metrics=ShotMetrics(motion=0.9), length=8.0),
        _shot("m1", 1, metrics=ShotMetrics(motion=0.1), length=2.0),
        _shot("m1", 2, metrics=ShotMetrics(motion=0.1), length=7.0),
    ]
    ranked = rank_shots(shots, "closer", 1)
    assert ranked[0].id == "hash_02"


def test_tie_breaks_by_id() -> None:
    shots = [
        _shot("m1", 2, metrics=ShotMetrics(motion=0.5, sharpness=0.5)),
        _shot("m1", 1, metrics=ShotMetrics(motion=0.5, sharpness=0.5)),
    ]
    ranked = rank_shots(shots, "site_detail", 2)
    assert [s.id for s in ranked] == ["hash_01", "hash_02"]
    assert score_shot(shots[0], "site_detail") == score_shot(shots[1], "site_detail")


def test_shots_rank_unknown_role_and_top_k(editor: Editor, media_file: Path) -> None:
    editor.import_file(str(media_file))
    mid = editor.media[0].id
    shots = [
        _shot(mid, 0, metrics=ShotMetrics(motion=0.9, sharpness=0.2)),
        _shot(mid, 1, metrics=ShotMetrics(motion=0.1, sharpness=0.9)),
        _shot(mid, 2, metrics=ShotMetrics(motion=0.3, sharpness=0.4)),
    ]
    write_manifest(editor._manifest_for(editor.media[0]), shots)
    bad = editor.shots_rank("highway")
    assert bad["ok"] is False
    all_roles = editor.shots_rank("hook", top_k=99)
    assert all_roles["ok"] is True
    assert len(all_roles["shots"]) == 3


def test_shots_rank_sheet_uses_only_candidates(editor: Editor, tmp_path: Path) -> None:
    media = touch_media(tmp_path / "src", "ride")
    editor.import_file(str(media))
    mid = editor.media[0].id
    keys = []
    shots = []
    for i, motion in enumerate((0.9, 0.1, 0.4)):
        kf = editor.store.keyframes_dir / f"k{i}.jpg"
        kf.parent.mkdir(parents=True, exist_ok=True)
        kf.write_bytes(b"\xff\xd8\xff" + b"\x00" * 120 + b"\xd9")
        keys.append(kf)
        shots.append(_shot(mid, i, metrics=ShotMetrics(motion=motion), keyframe=str(kf)))
    write_manifest(editor._manifest_for(editor.media[0]), shots)
    ranked = editor.shots_rank("journey", top_k=2, sheet=True)
    assert ranked["ok"] is True
    assert len(ranked["shots"]) == 2
    assert ranked["shots"][0]["metrics"]["motion"] == 0.9
    assert Path(ranked["path"]).exists()
    dest = Path(ranked["path"])
    assert dest.name == "rank_journey.jpg"
    blob = " ".join(" ".join(c) for c in editor.runner.calls)
    assert str(keys[0]) in blob
    assert str(keys[2]) in blob
    assert str(keys[1]) not in blob
