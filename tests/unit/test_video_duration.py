from __future__ import annotations

from pathlib import Path

from lc_editor.app import Editor
from lc_editor.models import MIN_VIDEO_DURATION_S
from tests.conftest import touch_media


def _add_video(editor: Editor, media_file: Path, duration_s: float) -> str:
    editor.import_file(str(media_file))
    editor.clip_add(media_id=editor.media[-1].id, duration_s=duration_s)
    return editor.timeline_get()["timeline"]["clips"][-1]["id"]


def test_new_project_defaults_video_floor(editor: Editor) -> None:
    assert editor.project_get()["project"]["min_video_duration_s"] == MIN_VIDEO_DURATION_S
    assert MIN_VIDEO_DURATION_S == 5.0


def test_clip_add_defaults_to_video_floor(editor: Editor, media_file: Path) -> None:
    editor.import_file(str(media_file))
    editor.clip_add(media_id=editor.media[-1].id)
    clip = editor.timeline_get()["timeline"]["clips"][0]
    assert clip["duration_s"] == MIN_VIDEO_DURATION_S


def test_video_4_9s_clip_set_duration_rejected(editor: Editor, media_file: Path) -> None:
    clip_id = _add_video(editor, media_file, 5.0)
    bad = editor.clip_set_duration(clip_id, 4.9)
    assert bad["ok"] is False
    assert any("SPEC-EDIT-25" in w for w in bad["warnings"])
    assert editor.timeline_get()["timeline"]["clips"][0]["duration_s"] == 5.0


def test_video_4_9s_lint_fails_review_and_export(editor: Editor, media_file: Path) -> None:
    _add_video(editor, media_file, 4.9)
    review = editor.review_report()
    assert review["ok"] is False
    assert any("SPEC-EDIT-25" in w for w in review["warnings"])
    clip = editor.store.timeline.clips[0]
    editor.store.timeline = editor.store.timeline.model_copy(
        update={"clips": [clip.model_copy(update={"duration_s": 5.0, "out_s": 5.0})]}
    )
    assert editor.review_report()["ok"] is True
    sneak = editor.store.timeline.clips[0]
    editor.store.timeline = editor.store.timeline.model_copy(
        update={"clips": [sneak.model_copy(update={"duration_s": 4.9, "out_s": 4.9})]}
    )
    exported = editor.export()
    assert exported["ok"] is False
    assert any("SPEC-EDIT-25" in w for w in exported["warnings"])


def test_still_1_5s_exempt_from_video_floor(editor: Editor, tmp_path: Path) -> None:
    still = touch_media(tmp_path / "src", "photo", ".jpg")
    editor.import_file(str(still))
    added = editor.clip_add(media_id=editor.media[-1].id, duration_s=1.5)
    assert added["ok"] is True
    clip_id = editor.timeline_get()["timeline"]["clips"][-1]["id"]
    set_ok = editor.clip_set_duration(clip_id, 1.5)
    assert set_ok["ok"] is True
    review = editor.review_report()
    assert not any("SPEC-EDIT-25" in w for w in review["warnings"])
    assert not any("SPEC-EDIT-25" in e for e in review.get("errors", []))


def test_project_set_changes_video_floor(tmp_path: Path, media_file: Path) -> None:
    from lc_editor.render.runner import FakeRunner

    editor = Editor(workspace=tmp_path, runner=FakeRunner(duration_s=12.0))
    editor.project_create(name="reel", project_dir=str(tmp_path / "reel"))
    clip_id = _add_video(editor, media_file, 5.0)
    lowered = editor.project_set(min_video_duration_s=4.0)
    assert lowered["ok"] is True
    assert editor.project_get()["project"]["min_video_duration_s"] == 4.0
    assert editor.clip_set_duration(clip_id, 4.5)["ok"] is True
    raised = editor.project_set(min_video_duration_s=6.0)
    assert raised["ok"] is True
    bad = editor.clip_set_duration(clip_id, 5.0)
    assert bad["ok"] is False
    assert any("SPEC-EDIT-25" in w for w in bad["warnings"])
    reset = editor.project_set(min_video_duration_s=0)
    assert reset["ok"] is True
    assert editor.project_get()["project"]["min_video_duration_s"] == MIN_VIDEO_DURATION_S


def test_whole_source_short_video_warns_only(editor: Editor, tmp_path: Path, runner) -> None:
    runner.duration_s = 4.0
    media = touch_media(tmp_path / "src", "short")
    editor.import_file(str(media))
    editor.clip_add(media_id=editor.media[-1].id, duration_s=4.0)
    review = editor.review_report()
    assert review["ok"] is True
    assert any("SPEC-EDIT-25" in w and "whole source" in w for w in review["warnings"])
    clip_id = editor.timeline_get()["timeline"]["clips"][0]["id"]
    hold = editor.clip_set_duration(clip_id, 4.0)
    assert hold["ok"] is True
    assert any("SPEC-EDIT-25" in w for w in hold["warnings"])
