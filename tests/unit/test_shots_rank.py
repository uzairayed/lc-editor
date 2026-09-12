from __future__ import annotations

from pathlib import Path

from lc_editor.analysis.manifest import Shot, ShotMetrics, write_manifest
from lc_editor.analysis.rank import ROLES, pool_for_role, rank_shots, score_shot
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


def test_rank_prefers_hd_when_scores_tie() -> None:
    sd = _shot("sd", 0, metrics=ShotMetrics(motion=0.5, sharpness=0.5))
    hd = _shot("hd", 1, metrics=ShotMetrics(motion=0.5, sharpness=0.5))
    sizes = {"sd": (512, 288), "hd": (1920, 1080)}
    ranked = rank_shots([sd, hd], "site_detail", 2, sizes=sizes)
    assert ranked[0].media_id == "hd"
    assert score_shot(hd, "site_detail", sizes=sizes) > score_shot(sd, "site_detail", sizes=sizes)


def test_process_roles_are_registered() -> None:
    for role in ("before", "wash", "detail", "after", "hero", "skip_face", "engine", "wheel", "interior", "machine"):
        assert role in ROLES


def test_before_role_prefers_tagged_media() -> None:
    before = _shot("b", 0, metrics=ShotMetrics(motion=0.4, sharpness=0.4), length=3.0)
    after = _shot("a", 1, metrics=ShotMetrics(motion=0.05, sharpness=0.95), length=3.0)
    roles = {"b": "before", "a": "after"}
    pooled = pool_for_role([before, after], "before", media_roles=roles)
    assert [s.media_id for s in pooled] == ["b"]
    ranked = rank_shots([before, after], "before", 2, media_roles=roles)
    assert ranked[0].media_id == "b"


def test_engine_role_boosts_engine_audio() -> None:
    ambient = _shot("m1", 0, metrics=ShotMetrics(motion=0.8, audio_class="ambient"), length=3.0)
    engine = _shot("m1", 1, metrics=ShotMetrics(motion=0.7, audio_class="engine"), length=3.0)
    ranked = rank_shots([ambient, engine], "engine", 1)
    assert ranked[0].id == "hash_01"


def test_shots_rank_unknown_role_and_top_k(editor: Editor, media_file: Path) -> None:
    editor.import_file(str(media_file))
    mid = editor.media[0].id
    shots = [
        _shot(mid, 0, metrics=ShotMetrics(motion=0.9, sharpness=0.2), length=3.0),
        _shot(mid, 1, metrics=ShotMetrics(motion=0.1, sharpness=0.9), length=3.0),
        _shot(mid, 2, metrics=ShotMetrics(motion=0.3, sharpness=0.4), length=3.0),
    ]
    write_manifest(editor._manifest_for(editor.media[0]), shots)
    bad = editor.shots_rank("highway")
    assert bad["ok"] is False
    all_roles = editor.shots_rank("hook", top_k=99)
    assert all_roles["ok"] is True
    assert len(all_roles["shots"]) == 3
    assert "score" in all_roles["shots"][0]
    assert "thumb" in all_roles["shots"][0]
    assert all_roles["shots"][0]["thumb"] == all_roles["shots"][0]["keyframe"]


def test_shots_rank_process_role_and_sheet(editor: Editor, tmp_path: Path) -> None:
    media = touch_media(tmp_path / "src", "detail")
    editor.import_file(str(media))
    editor.media_tag(editor.media[0].id, role="detail")
    mid = editor.media[0].id
    keys = []
    shots = []
    for i, sharp in enumerate((0.2, 0.9, 0.4)):
        kf = editor.store.keyframes_dir / f"k{i}.jpg"
        kf.parent.mkdir(parents=True, exist_ok=True)
        kf.write_bytes(b"\xff\xd8\xff" + b"\x00" * 120 + b"\xd9")
        keys.append(kf)
        shots.append(
            _shot(mid, i, metrics=ShotMetrics(motion=0.1, sharpness=sharp), keyframe=str(kf), length=3.0)
        )
    write_manifest(editor._manifest_for(editor.media[0]), shots)
    ranked = editor.shots_rank("detail", top_k=2, sheet=True)
    assert ranked["ok"] is True
    assert len(ranked["shots"]) == 2
    assert ranked["shots"][0]["metrics"]["sharpness"] == 0.9
    assert ranked["shots"][0]["score"] >= ranked["shots"][1]["score"]
    assert Path(ranked["path"]).exists()


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
        shots.append(_shot(mid, i, metrics=ShotMetrics(motion=motion), keyframe=str(kf), length=3.0))
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


def test_shots_rank_prefers_hd_source(editor: Editor, tmp_path: Path) -> None:
    sd = touch_media(tmp_path / "src", "sd")
    hd = touch_media(tmp_path / "src", "hd")
    editor.import_file(str(sd))
    editor.import_file(str(hd))
    editor.media[0] = editor.media[0].model_copy(update={"width": 512, "height": 288})
    editor.media[1] = editor.media[1].model_copy(update={"width": 1920, "height": 1080})
    metrics = ShotMetrics(motion=0.5, sharpness=0.5)
    write_manifest(
        editor._manifest_for(editor.media[0]),
        [_shot(editor.media[0].id, 0, metrics=metrics, length=3.0)],
    )
    write_manifest(
        editor._manifest_for(editor.media[1]),
        [_shot(editor.media[1].id, 1, metrics=metrics, length=3.0)],
    )
    ranked = editor.shots_rank("site_detail", top_k=2)
    assert ranked["ok"] is True
    assert ranked["shots"][0]["media_id"] == editor.media[1].id


def test_rank_prefers_same_role_hd_even_when_soft_scores_higher() -> None:
    soft = _shot("soft", 0, metrics=ShotMetrics(motion=0.05, sharpness=0.95), length=3.0)
    hd = _shot("hd", 1, metrics=ShotMetrics(motion=0.4, sharpness=0.35), length=3.0)
    sizes = {"soft": (512, 288), "hd": (1920, 1080)}
    assert score_shot(soft, "site_detail", sizes=sizes) > score_shot(hd, "site_detail", sizes=sizes)
    plain = rank_shots([soft, hd], "site_detail", 2, sizes=sizes)
    assert plain[0].media_id == "soft"
    ranked = rank_shots(
        [soft, hd],
        "site_detail",
        2,
        sizes=sizes,
        media_roles={"soft": "after", "hd": "after"},
    )
    assert ranked[0].media_id == "hd"
    other_role = rank_shots(
        [soft, hd],
        "site_detail",
        2,
        sizes=sizes,
        media_roles={"soft": "after", "hd": "before"},
    )
    assert other_role[0].media_id == "soft"
    other_day = rank_shots(
        [soft, hd],
        "site_detail",
        2,
        sizes=sizes,
        media_roles={"soft": "after", "hd": "after"},
        shoot_days={"soft": 1, "hd": 2},
    )
    assert other_day[0].media_id == "soft"
    same_day = rank_shots(
        [soft, hd],
        "site_detail",
        2,
        sizes=sizes,
        media_roles={"soft": "after", "hd": "after"},
        shoot_days={"soft": 1, "hd": 1},
    )
    assert same_day[0].media_id == "hd"


def test_shots_rank_prefers_same_role_hd_over_soft(editor: Editor, tmp_path: Path) -> None:
    sd = touch_media(tmp_path / "src", "sd")
    hd = touch_media(tmp_path / "src", "hd")
    editor.import_file(str(sd))
    editor.import_file(str(hd))
    editor.media[0] = editor.media[0].model_copy(update={"width": 512, "height": 288, "role": "after"})
    editor.media[1] = editor.media[1].model_copy(update={"width": 1920, "height": 1080, "role": "after"})
    write_manifest(
        editor._manifest_for(editor.media[0]),
        [_shot(editor.media[0].id, 0, metrics=ShotMetrics(motion=0.05, sharpness=0.95), length=3.0)],
    )
    write_manifest(
        editor._manifest_for(editor.media[1]),
        [_shot(editor.media[1].id, 1, metrics=ShotMetrics(motion=0.4, sharpness=0.35), length=3.0)],
    )
    ranked = editor.shots_rank("site_detail", top_k=2)
    assert ranked["ok"] is True
    assert ranked["shots"][0]["media_id"] == editor.media[1].id
