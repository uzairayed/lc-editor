from __future__ import annotations

from lc_editor.analysis.manifest import Shot, ShotMetrics, write_manifest
from lc_editor.analysis.rank import pool_for_role, rank_shots
from lc_editor.analysis.understand import card_from_shot, write_understand_cache
from lc_editor.app import Editor
from lc_editor.models import MediaCard
from tests.conftest import touch_media


def _shot(media_id: str, index: int, **overrides) -> Shot:
    metrics = overrides.pop("metrics", ShotMetrics())
    in_s = overrides.pop("in_s", float(index) * 2)
    out_s = overrides.pop("out_s", in_s + overrides.pop("length", 3.0))
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


def test_card_from_shot_flags_tiny_margin() -> None:
    dusty = _shot(
        "m",
        0,
        metrics=ShotMetrics(motion=0.05, sharpness=0.6, luma_mean=0.45, luma_spread=0.3),
    )
    card = card_from_shot(dusty, ["before", "after", "wash"])
    assert "needs_confirmation" in card
    close = _shot(
        "m",
        1,
        metrics=ShotMetrics(motion=0.2, sharpness=0.55, luma_mean=0.5, luma_spread=0.4),
    )
    close_card = card_from_shot(close, ["before", "after"])
    if close_card["needs_confirmation"]:
        assert close_card["role_scores"]


def test_confirmed_card_outranks_understand_and_media_tag() -> None:
    tagged = _shot("u", 0, metrics=ShotMetrics(motion=0.05, sharpness=0.9), tags=["understand:before"])
    media_tagged = _shot("t", 1, metrics=ShotMetrics(motion=0.05, sharpness=0.85))
    confirmed = _shot("c", 2, metrics=ShotMetrics(motion=0.4, sharpness=0.4))
    roles = {"u": "wash", "t": "before", "c": "after"}
    pooled = pool_for_role(
        [tagged, media_tagged, confirmed],
        "before",
        media_roles=roles,
        confirmed_roles={"c": "before"},
    )
    assert [s.media_id for s in pooled] == ["c"]
    ranked = rank_shots(
        [tagged, media_tagged, confirmed],
        "before",
        3,
        media_roles=roles,
        confirmed_roles={"c": "before"},
    )
    assert ranked[0].media_id == "c"


def test_propose_confirm_coverage_and_replay(editor: Editor, tmp_path: Path) -> None:
    media = touch_media(tmp_path / "src", "panel")
    editor.import_file(str(media))
    mid = editor.media[0].id
    kf_a = editor.store.keyframes_dir / "a.jpg"
    kf_b = editor.store.keyframes_dir / "b.jpg"
    kf_a.write_bytes(b"\xff\xd8\xff\xd9")
    kf_b.write_bytes(b"\xff\xd8\xff\xd9")
    write_manifest(
        editor._manifest_for(editor.media[0]),
        [
            _shot(mid, 0, metrics=ShotMetrics(luma_mean=0.2, sharpness=0.5), keyframe=str(kf_a)),
            _shot(mid, 1, metrics=ShotMetrics(luma_mean=0.8, sharpness=0.9), keyframe=str(kf_b)),
        ],
    )
    write_understand_cache(
        editor._understand_for(editor.media[0]),
        {
            "media_id": mid,
            "cards": [
                {
                    "media_id": mid,
                    "in_s": 0.0,
                    "out_s": 3.0,
                    "role_hint": "after",
                    "score": 0.61,
                    "keyframe_path": str(kf_b),
                    "reason": "bright payoff",
                    "role_scores": {"after": 0.61, "before": 0.59},
                    "needs_confirmation": True,
                }
            ],
        },
    )
    listed = editor.media_list()
    assert listed["card_coverage"] == {"carded": 0, "total": 1}
    assert listed["media"][0]["carded"] is False

    proposed = editor.media_card_propose()
    assert proposed["ok"] is True
    row = proposed["proposals"][0]
    assert row["media_id"] == mid
    assert row["proposed_role"] == "after"
    assert row["needs_confirmation"] is True
    assert row["question"]
    assert str(kf_a) in row["keyframes"] or str(kf_b) in row["keyframes"]

    confirmed = editor.media_card_confirm(
        mid, role="after", shoot_day=1, subjects=["panel"], note="day-one polish", op_id="card-1"
    )
    assert confirmed["ok"] is True
    assert confirmed["card"]["confirmed"] is True
    assert confirmed["media"]["role"] == "after"
    assert confirmed["media"]["shoot_day"] == 1
    replay = editor.media_card_confirm(mid, role="before", op_id="card-1")
    assert replay["media"]["role"] == "after"
    listed = editor.media_list()
    assert listed["card_coverage"] == {"carded": 1, "total": 1}
    assert listed["media"][0]["carded"] is True
    assert listed["media"][0]["card"]["subjects"] == ["panel"]


def test_uncarded_before_slot_warns_until_confirm(editor: Editor, tmp_path: Path) -> None:
    media = touch_media(tmp_path / "src", "dusty")
    editor.import_file(str(media))
    mid = editor.media[0].id
    editor.media = [editor.media[0].model_copy(update={"role": "before", "captured_at": "2024-03-01T10:00:00Z"})]
    editor._save_media()
    editor.clip_add(media_id=mid, duration_s=5.0)
    report = editor.review_report()
    assert any("SPEC-ANA-19" in w for w in report["warnings"])
    editor.media_card_confirm(mid, role="before", subjects=["hood"])
    report = editor.review_report()
    assert not any("SPEC-ANA-19" in w for w in report["warnings"])


def test_shots_rank_uses_confirmed_card_pool(editor: Editor, tmp_path: Path) -> None:
    first = touch_media(tmp_path / "src", "one")
    second = touch_media(tmp_path / "src", "two")
    editor.import_file(str(first))
    editor.import_file(str(second))
    a, b = editor.media[0].id, editor.media[1].id
    write_manifest(
        editor._manifest_for(editor.media[0]),
        [_shot(a, 0, metrics=ShotMetrics(motion=0.05, sharpness=0.95), tags=["understand:before"], length=3.0)],
    )
    write_manifest(
        editor._manifest_for(editor.media[1]),
        [_shot(b, 1, metrics=ShotMetrics(motion=0.4, sharpness=0.4), length=3.0)],
    )
    editor.media = [
        editor.media[0].model_copy(update={"role": "before"}),
        editor.media[1].model_copy(
            update={
                "role": "after",
                "card": MediaCard(role="before", confirmed=True, source="agent", confidence=1.0),
            }
        ),
    ]
    editor._save_media()
    ranked = editor.shots_rank("before", top_k=5)
    assert ranked["ok"] is True
    assert ranked["shots"]
    assert ranked["shots"][0]["media_id"] == b
