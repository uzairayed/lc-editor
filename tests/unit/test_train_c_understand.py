"""Train C: PROCESS_ROLES labeling + Director understand_timeline feed."""

from __future__ import annotations

from pathlib import Path

from lc_editor.analysis.manifest import Shot, ShotMetrics, write_manifest
from lc_editor.analysis.rank import (
    PROCESS_STORY_ORDER,
    UNDERSTAND_BOOST,
    pool_for_role,
    score_shot,
)
from lc_editor.analysis.understand import (
    DEFAULT_PROCESS_ROLES,
    best_role_hint,
    build_understand_timeline,
    card_from_shot,
    reason_for,
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


def test_default_process_roles_match_director_set() -> None:
    assert "engine" in DEFAULT_PROCESS_ROLES
    assert "hero" in DEFAULT_PROCESS_ROLES
    assert "skip_face" in DEFAULT_PROCESS_ROLES
    assert "before" in DEFAULT_PROCESS_ROLES
    assert PROCESS_STORY_ORDER[0] == "before"
    assert PROCESS_STORY_ORDER[-1] == "skip_face"


def test_process_roles_have_distinct_scores() -> None:
    dusty = _shot(
        "m",
        0,
        metrics=ShotMetrics(motion=0.05, sharpness=0.55, luma_mean=0.25, blur=0.45, luma_spread=0.5),
    )
    wet = _shot(
        "m",
        1,
        metrics=ShotMetrics(motion=0.75, sharpness=0.4, luma_mean=0.5, audio_class="ambient", luma_spread=0.4),
    )
    shiny = _shot(
        "m",
        2,
        metrics=ShotMetrics(motion=0.05, sharpness=0.9, luma_mean=0.85, blur=0.1, luma_spread=0.55),
    )
    engine = _shot(
        "m",
        3,
        metrics=ShotMetrics(motion=0.8, sharpness=0.3, audio_class="engine"),
    )
    assert best_role_hint(dusty, list(DEFAULT_PROCESS_ROLES))[0] == "before"
    assert best_role_hint(wet, list(DEFAULT_PROCESS_ROLES))[0] == "wash"
    assert best_role_hint(shiny, list(DEFAULT_PROCESS_ROLES))[0] in {"after", "hero"}
    assert best_role_hint(engine, list(DEFAULT_PROCESS_ROLES))[0] == "engine"
    card = card_from_shot(dusty, list(DEFAULT_PROCESS_ROLES))
    assert "role_scores" in card
    assert "dusty/dull" in reason_for(dusty, "before", card["score"], role_scores=card["role_scores"])


def test_pool_for_role_prefers_understand_tags() -> None:
    plain = _shot("m", 0, metrics=ShotMetrics(motion=0.05, sharpness=0.7, blur=0.3), length=3.0)
    tagged = _shot(
        "m",
        1,
        metrics=ShotMetrics(motion=0.05, sharpness=0.68, blur=0.32),
        length=3.0,
        tags=["understand:wheel"],
    )
    pooled = pool_for_role([plain, tagged], "wheel", media_roles={})
    assert [s.id for s in pooled] == [tagged.id]
    assert score_shot(tagged, "wheel") > score_shot(plain, "wheel")
    boost = score_shot(tagged, "wheel") - score_shot(
        tagged.model_copy(update={"tags": []}), "wheel"
    )
    assert abs(boost - UNDERSTAND_BOOST) < 1e-9


def test_build_understand_timeline_orders_process_story() -> None:
    cards = [
        {
            "media_id": "m2",
            "in_s": 0,
            "out_s": 2,
            "role_hint": "after",
            "score": 0.9,
            "keyframe_path": "a.jpg",
            "reason": "after",
            "role_scores": {"after": 0.9},
        },
        {
            "media_id": "m1",
            "in_s": 0,
            "out_s": 2,
            "role_hint": "before",
            "score": 0.7,
            "keyframe_path": "b.jpg",
            "reason": "before",
            "role_scores": {"before": 0.7},
        },
        {
            "media_id": "m1",
            "in_s": 4,
            "out_s": 6,
            "role_hint": "wash",
            "score": 0.8,
            "keyframe_path": "c.jpg",
            "reason": "wash",
            "role_scores": {"wash": 0.8},
        },
    ]
    timeline = build_understand_timeline(cards, top_per_role=1)
    assert timeline["roles_present"] == ["before", "wash", "after"]
    assert [b["role"] for b in timeline["beats"]] == ["before", "wash", "after"]
    assert timeline["order"] == list(PROCESS_STORY_ORDER)


def test_understand_timeline_from_cache(editor: Editor, tmp_path: Path) -> None:
    media = touch_media(tmp_path / "src", "story")
    editor.import_file(str(media))
    mid = editor.media[0].id
    shots = [
        _shot(mid, 0, metrics=ShotMetrics(motion=0.05, sharpness=0.5, luma_mean=0.2), length=4.0),
        _shot(mid, 1, metrics=ShotMetrics(motion=0.7, sharpness=0.4, audio_class="ambient"), length=4.0),
        _shot(mid, 2, metrics=ShotMetrics(motion=0.05, sharpness=0.9, luma_mean=0.85), length=4.0),
    ]
    for i, shot in enumerate(shots):
        kf = editor.store.keyframes_dir / f"c{i}.jpg"
        kf.write_bytes(b"\xff\xd8\xff\xd9")
        shots[i] = shot.model_copy(update={"keyframe": str(kf)})
    write_manifest(editor._manifest_for(editor.media[0]), shots)
    understood = editor.media_understand(budget_frames=16)
    assert understood["ok"] is True
    version = editor.timeline_get()["timeline_summary"]["version"]
    feed = editor.understand_timeline(top_per_role=1)
    assert feed["ok"] is True
    assert feed["timeline_summary"]["version"] == version
    assert feed["from_cache"] is True
    assert feed["beats"]
    assert feed["roles_present"]
    assert set(feed["roles_present"]).issubset(set(PROCESS_STORY_ORDER) | {"detail", "polish"})
    roles = [b["role"] for b in feed["beats"]]
    assert roles == sorted(roles, key=lambda r: PROCESS_STORY_ORDER.index(r) if r in PROCESS_STORY_ORDER else 99)
    for beat in feed["beats"]:
        for key in ("role", "media_id", "in_s", "out_s", "score", "keyframe_path", "reason", "source"):
            assert key in beat


def test_shots_rank_pool_is_understand_only(editor: Editor, tmp_path: Path) -> None:
    media = touch_media(tmp_path / "src", "rankc")
    editor.import_file(str(media))
    mid = editor.media[0].id
    plain = _shot(mid, 0, metrics=ShotMetrics(motion=0.05, sharpness=0.99), length=3.0)
    tagged = _shot(
        mid,
        1,
        metrics=ShotMetrics(motion=0.05, sharpness=0.2),
        length=3.0,
        tags=["understand:interior"],
    )
    write_manifest(editor._manifest_for(editor.media[0]), [plain, tagged])
    ranked = editor.shots_rank("interior", top_k=5)
    assert ranked["ok"] is True
    assert [s["id"] for s in ranked["shots"]] == [tagged.id]


def test_shots_search_lists_understand_first(editor: Editor, tmp_path: Path) -> None:
    media_a = touch_media(tmp_path / "src", "a")
    media_b = touch_media(tmp_path / "src", "b")
    editor.import_file(str(media_a))
    editor.import_file(str(media_b))
    a = editor.media[0].id
    b = editor.media[1].id
    shots_a = [_shot(a, 0, metrics=ShotMetrics(motion=0.1, sharpness=0.5), length=3.0)]
    shots_b = [
        _shot(b, 0, metrics=ShotMetrics(motion=0.1, sharpness=0.5), length=3.0, tags=["understand:machine"])
    ]
    write_manifest(editor._manifest_for(editor.media[0]), shots_a)
    write_manifest(editor._manifest_for(editor.media[1]), shots_b)
    found = editor.shots_search()
    assert found["ok"] is True
    assert found["shots"][0]["id"] == shots_b[0].id
