from __future__ import annotations

from pathlib import Path

from lc_editor.app import Editor
from lc_editor.render.runner import FakeRunner
from tests.conftest import touch_media


def test_spec_ses_01_mutation_envelope(editor: Editor, media_file: Path) -> None:
    editor.import_file(str(media_file))
    result = editor.clip_add(media_id=editor.media[0].id)
    assert set(result) >= {"ok", "timeline_summary", "warnings"}
    assert result["ok"] is True
    summary = result["timeline_summary"]
    assert set(summary) == {"version", "clip_count", "duration_s", "caption_count", "transition_count"}
    assert summary["clip_count"] == 1
    assert isinstance(result["warnings"], list)


def test_spec_ses_02_project_create_9_16(tmp_path: Path) -> None:
    ed = Editor(workspace=tmp_path, runner=FakeRunner())
    result = ed.project_create(name="karachi", aspect="9:16", project_dir=str(tmp_path / "k"))
    assert result["ok"] is True
    got = ed.project_get()
    project = got["project"]
    assert project["width"] == 1080
    assert project["height"] == 1920
    assert project["fps"] == 30
    assert project["allow_music"] is False


def test_spec_ses_03_allow_music_opt_in(editor: Editor) -> None:
    result = editor.project_set(allow_music=True)
    assert result["ok"] is True
    assert editor.project_get()["project"]["allow_music"] is True
    off = editor.project_set(allow_music=False)
    assert off["ok"] is True
    assert editor.project_get()["project"]["allow_music"] is False


def test_spec_ses_03_project_list(editor: Editor) -> None:
    listed = editor.project_list()
    assert listed["ok"] is True
    assert len(listed["projects"]) >= 1


def test_spec_ses_07_unknown_tool(editor: Editor) -> None:
    result = editor.call("raw_filter_complex")
    assert result["ok"] is False
    assert result["warnings"] == ["not implemented"]
