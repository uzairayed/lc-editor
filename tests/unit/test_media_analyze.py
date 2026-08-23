from __future__ import annotations

from pathlib import Path

from lc_editor.app import Editor
from lc_editor.render.jobs import source_proxy_hash
from lc_editor.render.runner import FakeRunner
from tests.conftest import touch_media


def _manifest(editor: Editor, media_id: str | None = None) -> Path:
    item = editor.media[0] if media_id is None else next(m for m in editor.media if m.id == media_id)
    src = Path(item.path)
    if not src.exists():
        src = Path(item.original_path)
    key = source_proxy_hash(src) if src.exists() else item.id
    return editor.store.analysis_dir / f"{key}.json"


def test_media_analyze_empty_metadata_fails_video(editor: Editor, media_file: Path) -> None:
    editor.import_file(str(media_file))
    editor.runner.empty_metadata = True
    version = editor.timeline_get()["timeline_summary"]["version"]
    result = editor.media_analyze()
    assert result["ok"] is False
    assert any("empty metadata" in w for w in result["warnings"])
    assert result["timeline_summary"]["version"] == version
    assert not _manifest(editor).exists()


def test_media_analyze_empty_project(editor: Editor) -> None:
    version = editor.timeline_get()["timeline_summary"]["version"]
    result = editor.media_analyze()
    assert result["ok"] is True
    assert result["shots"] == 0
    assert result["cached"] == []
    assert result["timeline_summary"]["version"] == version


def test_media_analyze_writes_manifest_and_keyframes(editor: Editor, media_file: Path) -> None:
    editor.import_file(str(media_file))
    version = editor.timeline_get()["timeline_summary"]["version"]
    result = editor.media_analyze()
    assert result["ok"] is True
    assert result["shots"] >= 1
    assert result["cached"] == [False]
    assert result["timeline_summary"]["version"] == version
    dest = _manifest(editor)
    assert dest.exists()
    listed = editor.shots_list()
    assert listed["ok"] is True
    assert len(listed["shots"]) == result["shots"]
    for shot in listed["shots"]:
        assert Path(shot["keyframe"]).exists()
        assert shot["in_s"] < shot["out_s"]


def test_media_analyze_second_call_is_cached(editor: Editor, media_file: Path) -> None:
    editor.import_file(str(media_file))
    first = editor.media_analyze()
    n = len(editor.runner.calls)
    second = editor.media_analyze()
    assert second["ok"] is True
    assert second["cached"] == [True]
    assert second["shots"] == first["shots"]
    assert len(editor.runner.calls) == n


def test_media_analyze_image_is_one_still_without_audio_pass(editor: Editor, tmp_path: Path) -> None:
    image = touch_media(tmp_path / "src", "still", ".jpg")
    editor.import_file(str(image))
    before = len(editor.runner.calls)
    result = editor.media_analyze()
    assert result["ok"] is True
    assert result["shots"] == 1
    blob = " ".join(" ".join(c) for c in editor.runner.calls[before:])
    assert "astats" not in blob
    assert "scdet" not in blob
    shot = editor.shots_list()["shots"][0]
    assert shot["metrics"]["audio_class"] == "silent"
    assert shot["duration_s"] == 2.5


def test_media_analyze_silent_video(tmp_path: Path) -> None:
    runner = FakeRunner(duration_s=5.0, has_audio=False)
    editor = Editor(workspace=tmp_path, runner=runner)
    editor.project_create(name="reel", project_dir=str(tmp_path / "reel"))
    media = touch_media(tmp_path / "src", "quiet")
    editor.import_file(str(media))
    assert editor.media[0].has_audio is False
    result = editor.media_analyze()
    assert result["ok"] is True
    for shot in editor.shots_list()["shots"]:
        assert shot["metrics"]["audio_class"] == "silent"
        assert shot["metrics"]["audio_rms_db"] is None


def test_media_analyze_ffmpeg_fail_writes_no_manifest(editor: Editor, media_file: Path) -> None:
    editor.import_file(str(media_file))
    version = editor.timeline_get()["timeline_summary"]["version"]
    editor.runner.fail = True
    result = editor.media_analyze()
    assert result["ok"] is False
    assert result["warnings"]
    assert result["timeline_summary"]["version"] == version
    assert not _manifest(editor).exists()


def test_media_analyze_batch_isolates_failure(editor: Editor, tmp_path: Path) -> None:
    a = touch_media(tmp_path / "src", "good")
    b = touch_media(tmp_path / "src", "bad")
    editor.import_file(str(a))
    editor.import_file(str(b))
    editor.runner.fail_inputs.append(Path(editor.media[1].proxy_path).name)
    result = editor.media_analyze()
    assert result["ok"] is False
    assert any(editor.media[1].id in w for w in result["warnings"])
    assert _manifest(editor, editor.media[0].id).exists()
    assert not _manifest(editor, editor.media[1].id).exists()
    listed = editor.shots_list()
    assert all(s["media_id"] == editor.media[0].id for s in listed["shots"])


def test_media_analyze_op_id_replay(editor: Editor, media_file: Path) -> None:
    editor.import_file(str(media_file))
    first = editor.media_analyze(op_id="ana-1")
    n = len(editor.runner.calls)
    again = editor.media_analyze(op_id="ana-1")
    assert again["ok"] == first["ok"]
    assert again["shots"] == first["shots"]
    assert len(editor.runner.calls) == n


def test_media_analyze_builds_missing_proxy(editor: Editor, media_file: Path) -> None:
    editor.import_file(str(media_file))
    item = editor.media[0]
    proxy = Path(item.proxy_path)
    proxy.unlink()
    item.proxy_path = ""
    editor._save_media()
    result = editor.media_analyze()
    assert result["ok"] is True
    assert Path(editor.media[0].proxy_path).exists()


def test_media_remove_hides_shots(editor: Editor, media_file: Path) -> None:
    editor.import_file(str(media_file))
    editor.media_analyze()
    assert editor.shots_list()["shots"]
    editor.media_remove(editor.media[0].id)
    listed = editor.shots_list()
    assert listed["ok"] is True
    assert listed["shots"] == []


def test_shots_list_before_analyze_warns(editor: Editor, media_file: Path) -> None:
    editor.import_file(str(media_file))
    listed = editor.shots_list()
    assert listed["ok"] is True
    assert listed["shots"] == []
    assert "not analyzed" in listed["warnings"]


def test_media_analyze_unicode_filename(editor: Editor, tmp_path: Path) -> None:
    media = touch_media(tmp_path / "src", "café ride")
    imported = editor.import_file(str(media))
    assert imported["ok"]
    result = editor.media_analyze()
    assert result["ok"] is True
    assert result["shots"] >= 1


def test_media_analyze_burst_cover_only(editor: Editor, tmp_path: Path) -> None:
    folder = tmp_path / "burst"
    touch_media(folder, "PXL_20240101_BURST001", ".jpg")
    touch_media(folder, "PXL_20240101_BURST001_COVER", ".jpg")
    imported = editor.import_folder(str(folder))
    assert imported["ok"]
    assert len(imported["media"]) == 1
    result = editor.media_analyze()
    assert result["ok"] is True
    assert result["shots"] == 1
    assert len(editor.shots_list()["shots"]) == 1
