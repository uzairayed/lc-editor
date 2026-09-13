from __future__ import annotations

from pathlib import Path

from lc_editor.app import Editor
from lc_editor.presets import list_presets, load_preset, project_fields_from_preset
from lc_editor.render.runner import FakeRunner
from tests.conftest import touch_media


def test_spec_ses_12_karachi_is_optional(tmp_path: Path) -> None:
    ed = Editor(workspace=tmp_path, runner=FakeRunner())
    ed.project_create(name="plain", project_dir=str(tmp_path / "plain"))
    project = ed.project_get()["project"]
    assert project["preset"] is None
    assert project["allow_music"] is False
    assert project["duration_cap_s"] == 60.0
    applied = ed.project_set(preset="karachi")
    assert applied["ok"] is True
    got = ed.project_get()["project"]
    assert got["preset"] == "karachi"
    assert got["grade_preset"] == "motovlog"
    assert got["allow_music"] is False


def test_spec_edit_26_process_preset_on_create(tmp_path: Path) -> None:
    ed = Editor(workspace=tmp_path, runner=FakeRunner())
    created = ed.project_create(name="detail", project_dir=str(tmp_path / "detail"), preset="process")
    assert created["ok"] is True
    assert created["preset"]["id"] == "process"
    project = ed.project_get()["project"]
    assert project["preset"] == "process"
    assert project["duration_cap_s"] == 180.0
    assert project["caption_contrast"] == "lenient"
    assert project["min_video_duration_s"] == 5.0
    assert project["allow_music"] is False
    assert project["loudnorm"] == "cinema"
    assert project["grade_preset"] == "neutral"


def test_spec_edit_26_process_preset_via_set(tmp_path: Path) -> None:
    ed = Editor(workspace=tmp_path, runner=FakeRunner())
    ed.project_create(name="plain", project_dir=str(tmp_path / "plain"))
    before = ed.project_get()["project"]
    assert before["duration_cap_s"] == 60.0
    assert before["preset"] is None
    applied = ed.project_set(preset="process")
    assert applied["ok"] is True
    got = ed.project_get()["project"]
    assert got["preset"] == "process"
    assert got["duration_cap_s"] == 180.0
    assert got["caption_contrast"] == "lenient"
    assert got["min_video_duration_s"] == 5.0
    assert got["allow_music"] is False
    assert got["loudnorm"] == "cinema"
    # Owner may still flip music on after the preset.
    assert ed.project_set(allow_music=True)["ok"] is True
    assert ed.project_get()["project"]["allow_music"] is True


def test_spec_edit_26_unset_preset_keeps_short_form(tmp_path: Path) -> None:
    ed = Editor(workspace=tmp_path, runner=FakeRunner())
    ed.project_create(name="short", project_dir=str(tmp_path / "short"))
    project = ed.project_get()["project"]
    assert project["preset"] is None
    assert project["duration_cap_s"] == 60.0
    assert project["min_video_duration_s"] == 5.0
    assert project["caption_contrast"] == "lenient"
    assert project["loudnorm"] == "cinema"
    assert project["allow_music"] is False


def test_process_preset_json_and_fields() -> None:
    assert "process" in list_presets()
    data = load_preset("process")
    fields = project_fields_from_preset(data)
    assert fields["duration_cap_s"] == 180.0
    assert fields["loudnorm"] == "cinema"
    assert fields["allow_music"] is False
    # Preset must never force music on.
    assert project_fields_from_preset({**data, "allow_music": True}).get("allow_music") is None


def test_spec_ses_06_pxl_burst_keeps_cover_only(editor: Editor, tmp_path: Path) -> None:
    folder = tmp_path / "pxl"
    cover = touch_media(folder, "PXL_20240101_120000000.BURST_001_COVER", ".jpg")
    touch_media(folder, "PXL_20240101_120000000.BURST_002", ".jpg")
    touch_media(folder, "PXL_20240101_120000000.BURST_003", ".jpg")
    extra = touch_media(folder, "PXL_20240101_130000000", ".jpg")
    result = editor.import_folder(str(folder))
    assert result["ok"] is True
    names = [Path(p).name for p in result["imported"]]
    assert cover.name in names
    assert extra.name in names
    assert len(result["skipped"]) == 2
    assert result["deduped"]
    assert len(result["media"]) == 2
