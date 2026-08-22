from __future__ import annotations

from pathlib import Path

from lc_editor.app import Editor
from lc_editor.render.runner import FakeRunner
from tests.conftest import touch_media


def test_spec_ses_12_karachi_is_optional(tmp_path: Path) -> None:
    ed = Editor(workspace=tmp_path, runner=FakeRunner())
    ed.project_create(name="plain", project_dir=str(tmp_path / "plain"))
    project = ed.project_get()["project"]
    assert project["preset"] is None
    assert project["allow_music"] is False
    applied = ed.project_set(preset="karachi")
    assert applied["ok"] is True
    got = ed.project_get()["project"]
    assert got["preset"] == "karachi"
    assert got["grade_preset"] == "motovlog"
    assert got["allow_music"] is False


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
