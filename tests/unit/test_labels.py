from __future__ import annotations

from pathlib import Path

from lc_editor.analysis.labels import GUI_DOMAIN_TOOLS, resolve_labels
from lc_editor.analysis.manifest import Shot, ShotMetrics, write_manifest
from lc_editor.analysis.rank import pool_for_role
from lc_editor.analysis.understand import write_understand_cache
from lc_editor.app import Editor
from lc_editor.models import MediaCard, ShotCard
from lc_editor.server import TOOLS
from tests.conftest import touch_media


def _shot(media_id: str, index: int, **overrides) -> Shot:
    metrics = overrides.pop("metrics", ShotMetrics())
    in_s = overrides.pop("in_s", float(index) * 2)
    out_s = overrides.pop("out_s", in_s + overrides.pop("length", 3.0))
    data = {
        "id": overrides.pop("id", f"hash_{index:02d}"),
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


def test_gui_domain_tools_are_registered() -> None:
    assert set(GUI_DOMAIN_TOOLS).issubset(TOOLS)


def test_precedence_shot_over_media_over_analysis_over_folder() -> None:
    item = type("M", (), {})()
    item.id = "m1"
    item.kind = "video"
    item.role = None
    item.shoot_day = None
    item.captured_at = None
    item.original_path = "/album/before/day1/clip.mp4"
    item.path = item.original_path
    item.card = MediaCard(role="wash", shoot_day=1, confirmed=True, source="owner")
    shot = _shot("m1", 0, tags=["understand:detail"])
    shot_card = ShotCard(shot_id=shot.id, media_id="m1", role="after", confirmed=True)
    cards = [{"in_s": 0, "out_s": 3, "role_hint": "detail", "score": 0.9}]
    resolved = resolve_labels(item, shot, shot_card=shot_card, understand_cards=cards)
    assert resolved["role"]["value"] == "after"
    assert resolved["role"]["source"] == "shot_card"
    resolved = resolve_labels(item, shot, understand_cards=cards)
    assert resolved["role"]["value"] == "wash"
    assert resolved["role"]["source"] == "media_card"
    item.card = MediaCard(role="before", source="folder", confirmed=False)
    resolved = resolve_labels(item, shot, understand_cards=cards)
    assert resolved["role"]["value"] == "detail"
    assert resolved["role"]["source"] == "analysis"
    resolved = resolve_labels(item, None, understand_cards=[])
    assert resolved["role"]["source"] == "folder"
    assert resolved["role"]["value"] == "before"


def test_shot_card_survives_reanalysis_and_does_not_bump_timeline(editor: Editor, tmp_path: Path) -> None:
    media = touch_media(tmp_path / "src", "panel")
    editor.import_file(str(media))
    mid = editor.media[0].id
    version = editor.store.timeline.version
    shot = _shot(mid, 0, id="abc_00")
    write_manifest(editor._manifest_for(editor.media[0]), [shot])
    confirmed = editor.shot_card_confirm(shot.id, role="before", subjects=["hood"], op_id="shot-1")
    assert confirmed["ok"] is True
    assert confirmed["timeline_summary"]["version"] == version
    replay = editor.shot_card_confirm(shot.id, role="after", op_id="shot-1")
    assert replay["card"]["role"] == "before"
    write_manifest(editor._manifest_for(editor.media[0]), [shot])
    got = editor.label_get(shot_id=shot.id)
    assert got["label"]["role"]["value"] == "before"
    assert got["label"]["role"]["source"] == "shot_card"
    assert (editor.store.root / "shot_cards.json").exists()
    editor.project_open(str(editor.store.root))
    assert editor.shot_cards[shot.id].role == "before"


def test_label_queue_confirm_undo_and_readiness(editor: Editor, tmp_path: Path) -> None:
    media = touch_media(tmp_path / "src" / "before", "dusty")
    editor.import_file(str(media))
    mid = editor.media[0].id
    kf = editor.store.keyframes_dir / "k.jpg"
    kf.write_bytes(b"\xff\xd8\xff\xd9")
    write_manifest(
        editor._manifest_for(editor.media[0]),
        [_shot(mid, 0, id="abc_00", keyframe=str(kf), tags=["understand:before"])],
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
                    "role_hint": "before",
                    "score": 0.6,
                    "needs_confirmation": True,
                    "role_scores": {"before": 0.6, "after": 0.58},
                }
            ],
        },
    )
    queued = editor.label_queue(filter="needs_confirmation")
    assert queued["ok"] is True
    assert queued["items"]
    ready = editor.label_readiness()
    assert ready["ready"] is False
    editor.media_card_confirm(mid, role="before", shoot_day=1, subjects=["hood"], source="owner")
    editor.shot_card_confirm("abc_00", role="after", note="payoff beat")
    got = editor.label_get(shot_id="abc_00")
    assert got["label"]["role"]["value"] == "after"
    conflicts = editor.label_conflicts()
    assert conflicts["conflicts"]
    editor.labels_undo()
    got = editor.label_get(shot_id="abc_00")
    assert got["label"]["role"]["source"] != "shot_card"
    editor.labels_bulk_confirm([{"media_id": mid, "role": "wash", "subjects": ["panel"]}])
    listed = editor.media_list()
    assert listed["media"][0]["card"]["role"] == "wash"
    editor.labels_clear(media_id=mid)
    listed = editor.media_list()
    assert listed["media"][0]["carded"] is False


def test_rank_and_search_use_confirmed_shot_override(editor: Editor, tmp_path: Path) -> None:
    first = touch_media(tmp_path / "src", "one")
    editor.import_file(str(first))
    mid = editor.media[0].id
    wash = _shot(mid, 0, id="abc_00", metrics=ShotMetrics(motion=0.8), tags=["understand:wash"], length=3.0)
    after = _shot(mid, 1, id="abc_01", metrics=ShotMetrics(motion=0.1, sharpness=0.2), length=3.0)
    write_manifest(editor._manifest_for(editor.media[0]), [wash, after])
    editor.media = [
        editor.media[0].model_copy(
            update={"role": "wash", "card": MediaCard(role="wash", confirmed=True, source="owner")}
        )
    ]
    editor._save_media()
    editor.shot_card_confirm("abc_01", role="before")
    ranked = editor.shots_rank("before", top_k=5)
    assert ranked["ok"] is True
    assert ranked["shots"][0]["id"] == "abc_01"
    search = editor.shots_search(role="before")
    assert any(row["id"] == "abc_01" for row in search["shots"])
    pooled = pool_for_role(
        [wash, after],
        "wash",
        confirmed_roles={mid: "wash"},
        confirmed_shot_roles={"abc_01": "before"},
    )
    assert [s.id for s in pooled] == ["abc_00"]
