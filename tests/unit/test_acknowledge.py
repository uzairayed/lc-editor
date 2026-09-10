from __future__ import annotations

from pathlib import Path

from lc_editor.analysis.manifest import Shot, ShotMetrics, write_manifest
from lc_editor.app import Editor
from lc_editor.lint.review import acknowledge_errors
from lc_editor.models import Clip, MIN_VIDEO_DURATION_S, Project, SHOT_ACK_MIN_S, STILL_ACK_MIN_S, Timeline
from tests.conftest import touch_media


def test_clip_add_defaults_to_ack_floor(editor: Editor, media_file: Path) -> None:
    editor.import_file(str(media_file))
    editor.clip_add(media_id=editor.media[-1].id)
    clip = editor.timeline_get()["timeline"]["clips"][0]
    assert clip["duration_s"] == MIN_VIDEO_DURATION_S


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
    editor.project_set(min_video_duration_s=2.4)
    editor.import_file(str(media_file))
    mid = editor.media[-1].id
    for _ in range(4):
        editor.clip_add(media_id=mid, duration_s=2.4)
    blocked = editor.review_report()
    assert blocked["ok"] is False
    assert any("SPEC-EDIT-ACK-02" in w for w in blocked["warnings"])
    assert blocked["report"]["density_relaxed"] is False
    allowed = editor.review_report(allow_dense=True)
    assert allowed["ok"] is True
    assert allowed["report"]["density_relaxed"] is True
    assert allowed["report"]["density_reason"] == "allow_dense"


def _dense_clips(n: int = 4, duration_s: float = 2.4) -> Timeline:
    return Timeline(clips=[Clip(id=f"c{i}", media_id="m", duration_s=duration_s) for i in range(n)])


def test_process_floor_relaxes_density_by_default() -> None:
    timeline = _dense_clips()
    project = Project(id="p", name="reel")
    assert project.min_video_duration_s == MIN_VIDEO_DURATION_S
    assert acknowledge_errors(timeline, None, project=project) == []
    enforced = acknowledge_errors(timeline, None, project=project, allow_dense=False)
    assert any("SPEC-EDIT-ACK-02" in e for e in enforced)


def test_process_timeline_many_five_second_clips(editor: Editor, media_file: Path) -> None:
    editor.import_file(str(media_file))
    mid = editor.media[-1].id
    for _ in range(8):
        editor.clip_add(media_id=mid, duration_s=5.0)
    result = editor.review_report()
    assert result["ok"] is True
    assert not any("SPEC-EDIT-ACK-02" in w for w in result["warnings"])
    assert not any("SPEC-EDIT-ACK-02" in e for e in result["errors"])
    assert result["report"]["density_relaxed"] is True
    assert result["report"]["density_reason"] == "min_video_duration_s"


def test_default_project_dense_stills_pass_without_allow_dense(editor: Editor, tmp_path: Path) -> None:
    still = touch_media(tmp_path / "src", "photo", ".jpg")
    editor.import_file(str(still))
    mid = editor.media[-1].id
    for _ in range(4):
        editor.clip_add(media_id=mid, duration_s=2.5)
    result = editor.review_report()
    assert result["ok"] is True
    assert not any("SPEC-EDIT-ACK-02" in w for w in result["warnings"])
    assert result["report"]["density_relaxed"] is True
    assert result["report"]["density_reason"] == "min_video_duration_s"
    enforced = editor.review_report(allow_dense=False)
    assert enforced["ok"] is False
    assert any("SPEC-EDIT-ACK-02" in w for w in enforced["warnings"])
    assert enforced["report"]["density_relaxed"] is False


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
    assert MIN_VIDEO_DURATION_S == 5.0
