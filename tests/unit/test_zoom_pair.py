from __future__ import annotations

from pathlib import Path

from lc_editor.app import Editor
from lc_editor.models import Clip, MediaItem, Project
from lc_editor.render import motion as motion_mod
from lc_editor.render.graph import clip_video_filters
from lc_editor.render.motion import zoom_hit_filter
from lc_editor.render.runner import FakeRunner


def _long_editor(tmp_path: Path) -> Editor:
    ed = Editor(workspace=tmp_path, runner=FakeRunner(duration_s=12.0))
    ed.project_create(name="reel", project_dir=str(tmp_path / "reel"))
    return ed


def _add(editor: Editor, media_file: Path, duration_s: float) -> str:
    if not editor.media:
        editor.import_file(str(media_file))
    editor.clip_add(media_id=editor.media[-1].id, duration_s=duration_s)
    return editor.timeline_get()["timeline"]["clips"][-1]["id"]


def test_spec_rnd_20_zoom_in_is_cubic_not_linear() -> None:
    graph = zoom_hit_filter("zoom_in")
    assert "pow" in graph
    compact = graph.replace(" ", "")
    assert "1+0.1*min(1,n/12)" not in compact
    assert "1+0.14*min(1" not in compact
    assert "27" in graph
    clip = Clip(id="c1", media_id="m1", motion="zoom_in", duration_s=4.0)
    media = MediaItem(id="m1", path="x.mp4", original_path="x.mp4", width=1920, height=1080)
    filt = clip_video_filters(clip, media, [], Project(id="p", name="n"))
    assert "pow" in filt


def test_spec_rnd_20_zoom_pair_returns_to_one() -> None:
    pair = getattr(motion_mod, "zoom_pair_filter", None)
    assert callable(pair)
    graph = pair(duration_s=6.0, amount=1.10, frames_in=27, frames_out=27, at_s=0.9)
    assert "pow" in graph
    assert "1+0.1" in graph.replace(" ", "") or "0.1" in graph
    clip = Clip(
        id="c1",
        media_id="m1",
        motion="zoom_pair",
        duration_s=6.0,
        zoom_amount=1.10,
        zoom_frames=27,
        zoom_frames_out=27,
        zoom_at_s=0.9,
    )
    media = MediaItem(id="m1", path="x.mp4", original_path="x.mp4", width=1920, height=1080)
    filt = clip_video_filters(clip, media, [], Project(id="p", name="n"))
    assert "pow" in filt


def test_spec_edit_21_zoom_pair_tool(tmp_path: Path, media_file: Path) -> None:
    editor = _long_editor(tmp_path)
    clip_id = _add(editor, media_file, 6.0)
    out = editor.motion_zoom_pair(clip_id)
    assert out["ok"] is True
    clip = editor.timeline_get()["timeline"]["clips"][-1]
    assert clip["motion"] == "zoom_pair"
    assert clip["zoom_amount"] == 1.10
    assert clip["zoom_frames"] == 27
    short_id = _add(editor, media_file, 2.0)
    rejected = editor.motion_zoom_pair(short_id)
    assert rejected["ok"] is False


def test_spec_edit_21_review_fails_midreel_zoom_in(tmp_path: Path, media_file: Path) -> None:
    editor = _long_editor(tmp_path)
    first = _add(editor, media_file, 4.0)
    _add(editor, media_file, 4.0)
    assert editor.motion_zoom_in(first)["ok"] is True
    review = editor.review_report()
    assert review["ok"] is False
    assert any("zoom_in" in w.lower() or "SPEC-EDIT-21" in w or "SPEC-RND-20" in w for w in review["warnings"] + review.get("errors", []))


def test_spec_edit_21_suggest_pair_none_and_skip_adjacent(tmp_path: Path, media_file: Path) -> None:
    editor = _long_editor(tmp_path)
    a = _add(editor, media_file, 6.0)
    b = _add(editor, media_file, 6.0)
    short = _add(editor, media_file, 1.5)
    suggested = editor.motion_zoom_suggest()
    assert suggested["ok"] is True
    by_id = {row["clip_id"]: row for row in suggested["suggestions"]}
    assert by_id[a]["action"] == "pair"
    assert by_id[b]["action"] == "none"
    assert by_id[short]["action"] == "none"
    actions = [row["action"] for row in suggested["suggestions"]]
    assert actions.count("pair") <= 1


def test_spec_edit_21_suggest_none_when_protect(tmp_path: Path, media_file: Path) -> None:
    editor = _long_editor(tmp_path)
    clip_id = _add(editor, media_file, 6.0)
    editor.grade_protect(clip_id, True)
    suggested = editor.motion_zoom_suggest()
    row = suggested["suggestions"][0]
    assert row["action"] == "none"
    assert any("protect" in r or "face" in r or "margin" in r for r in row["reason"])
