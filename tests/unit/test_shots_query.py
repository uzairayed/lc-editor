from __future__ import annotations

from pathlib import Path

from lc_editor.analysis.manifest import Shot, ShotMetrics, write_manifest
from lc_editor.app import Editor
from tests.conftest import touch_media


def _shot(media_id: str, index: int, **overrides) -> Shot:
    metrics = overrides.pop("metrics", ShotMetrics())
    in_s = overrides.pop("in_s", float(index))
    out_s = overrides.pop("out_s", in_s + 2.0)
    data = {
        "id": f"hash_{index}",
        "media_id": media_id,
        "in_s": in_s,
        "out_s": out_s,
        "duration_s": round(out_s - in_s, 4),
        "keyframe": f"/tmp/hash_{index}.jpg",
        "metrics": metrics,
    }
    data.update(overrides)
    return Shot.model_validate(data)


def _plant(editor: Editor, item, shots: list[Shot]) -> None:
    write_manifest(editor._manifest_for(item), shots)


def test_shots_search_filters_and_empty_ok(editor: Editor, media_file: Path) -> None:
    editor.import_file(str(media_file))
    mid = editor.media[0].id
    _plant(
        editor,
        editor.media[0],
        [
            _shot(mid, 0, metrics=ShotMetrics(motion=0.1), in_s=0.0, out_s=1.0),
            _shot(mid, 1, metrics=ShotMetrics(motion=0.8, audio_class="engine"), in_s=1.0, out_s=4.0),
            _shot(mid, 2, metrics=ShotMetrics(motion=0.4, audio_class="ambient"), in_s=4.0, out_s=6.0),
        ],
    )
    motion = editor.shots_search(min_motion=0.5)
    assert motion["ok"] is True
    assert [s["id"] for s in motion["shots"]] == ["hash_1"]

    audio = editor.shots_search(audio_class="ambient")
    assert [s["id"] for s in audio["shots"]] == ["hash_2"]

    duration = editor.shots_search(min_duration_s=2.5, max_duration_s=4.0)
    assert [s["id"] for s in duration["shots"]] == ["hash_1"]

    kind = editor.shots_search(kind="video")
    assert len(kind["shots"]) == 3
    none = editor.shots_search(kind="image")
    assert none["ok"] is True
    assert none["shots"] == []

    limited = editor.shots_search(sort="motion", limit=1)
    assert [s["id"] for s in limited["shots"]] == ["hash_0"]


def test_shots_search_contradictory_filters(editor: Editor, media_file: Path) -> None:
    editor.import_file(str(media_file))
    _plant(editor, editor.media[0], [_shot(editor.media[0].id, 0)])
    bad = editor.shots_search(min_duration_s=3.0, max_duration_s=1.0)
    assert bad["ok"] is False
    assert bad["warnings"]
    motion = editor.shots_search(min_motion=0.9, max_motion=0.1)
    assert motion["ok"] is False


def test_shots_search_deterministic_order(editor: Editor, tmp_path: Path) -> None:
    a = touch_media(tmp_path / "src", "a")
    b = touch_media(tmp_path / "src", "b")
    editor.import_file(str(a))
    editor.import_file(str(b))
    _plant(
        editor,
        editor.media[0],
        [_shot(editor.media[0].id, 1, in_s=2.0, out_s=4.0), _shot(editor.media[0].id, 0, in_s=0.0, out_s=2.0)],
    )
    _plant(editor, editor.media[1], [_shot(editor.media[1].id, 0, in_s=0.0, out_s=2.0)])
    listed = editor.shots_search()
    ids = [s["id"] for s in listed["shots"]]
    assert ids == ["hash_0", "hash_1", "hash_0"]
    assert [s["media_id"] for s in listed["shots"]] == [
        editor.media[0].id,
        editor.media[0].id,
        editor.media[1].id,
    ]
    again = editor.shots_search()
    assert [s["id"] for s in again["shots"]] == ids
