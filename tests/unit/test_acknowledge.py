from __future__ import annotations

from pathlib import Path

from lc_editor.analysis.manifest import Shot, ShotMetrics, write_manifest
from lc_editor.app import Editor
from lc_editor.models import SHOT_ACK_MIN_S, STILL_ACK_MIN_S
from tests.conftest import touch_media


def test_clip_add_defaults_to_ack_floor(editor: Editor, media_file: Path) -> None:
    editor.import_file(str(media_file))
    editor.clip_add(media_id=editor.media[-1].id)
    clip = editor.timeline_get()["timeline"]["clips"][0]
    assert clip["duration_s"] == SHOT_ACK_MIN_S


def test_ack_fragment_is_review_error(editor: Editor, media_file: Path) -> None:
    editor.import_file(str(media_file))
    editor.clip_add(media_id=editor.media[-1].id, duration_s=1.16)
    result = editor.review_report()
    assert result["ok"] is False
    assert any("SPEC-EDIT-ACK-01" in w for w in result["warnings"])


def test_ack_whole_source_is_warning(editor: Editor, tmp_path: Path, runner) -> None:
    runner.duration_s = 1.5
    media = touch_media(tmp_path / "src", "short")
    editor.import_file(str(media))
    editor.clip_add(media_id=editor.media[-1].id, duration_s=1.5)
    result = editor.review_report()
    assert result["ok"] is True
    assert any("SPEC-EDIT-ACK-01" in w for w in result["warnings"])


def test_density_cap_and_allow_dense(editor: Editor, media_file: Path) -> None:
    editor.import_file(str(media_file))
    mid = editor.media[-1].id
    for _ in range(4):
        editor.clip_add(media_id=mid, duration_s=2.4)
    blocked = editor.review_report()
    assert blocked["ok"] is False
    assert any("SPEC-EDIT-ACK-02" in w for w in blocked["warnings"])
    allowed = editor.review_report(allow_dense=True)
    assert allowed["ok"] is True


def test_shots_rank_drops_short_video_unless_pool_empty(editor: Editor, media_file: Path) -> None:
    editor.import_file(str(media_file))
    mid = editor.media[0].id
    shots = [
        Shot(
            id="hash_00",
            media_id=mid,
            in_s=0.0,
            out_s=1.16,
            duration_s=1.16,
            keyframe="/tmp/a.jpg",
            metrics=ShotMetrics(motion=0.9),
        ),
        Shot(
            id="hash_01",
            media_id=mid,
            in_s=2.0,
            out_s=5.0,
            duration_s=3.0,
            keyframe="/tmp/b.jpg",
            metrics=ShotMetrics(motion=0.4),
        ),
    ]
    write_manifest(editor._manifest_for(editor.media[0]), shots)
    ranked = editor.shots_rank("journey", top_k=2)
    assert [s["id"] for s in ranked["shots"]] == ["hash_01"]

    write_manifest(editor._manifest_for(editor.media[0]), shots[:1])
    fallback = editor.shots_rank("journey", top_k=2)
    assert [s["id"] for s in fallback["shots"]] == ["hash_00"]
    assert any("acknowledge floor" in w for w in fallback["warnings"])


def test_still_ack_constant() -> None:
    assert STILL_ACK_MIN_S == 2.2
    assert SHOT_ACK_MIN_S == 2.4
