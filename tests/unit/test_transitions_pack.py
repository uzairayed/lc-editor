from __future__ import annotations

from pathlib import Path

from lc_editor.app import Editor
from lc_editor.render.compositor import build_assemble_command
from lc_editor.render.jobs import render_clip_intermediate
from lc_editor.render.runner import FakeRunner
from lc_editor.render.transitions import fade_frames, source_hold_filter, whip_filter
from tests.conftest import touch_media


def _add(editor: Editor, media_file: Path, duration_s: float = 5.0) -> str:
    editor.import_file(str(media_file))
    mid = editor.media[-1].id
    editor.clip_add(media_id=mid, duration_s=duration_s)
    return editor.timeline_get()["timeline"]["clips"][-1]["id"]


def test_transition_set_cut_clears(editor: Editor, media_file: Path) -> None:
    a = _add(editor, media_file)
    _add(editor, media_file)
    assert editor.transition_set(from_clip_id=a, kind="whip")["ok"] is True
    assert editor.timeline_get()["timeline"]["transitions"][a] == "whip"
    cleared = editor.transition_set(from_clip_id=a, kind="cut")
    assert cleared["ok"] is True
    assert a not in editor.timeline_get()["timeline"]["transitions"]


def test_transition_set_fade_and_duration(editor: Editor, media_file: Path) -> None:
    a = _add(editor, media_file)
    _add(editor, media_file)
    ok = editor.transition_set(from_clip_id=a, kind="fade", duration_s=8 / 30)
    assert ok["ok"] is True
    tl = editor.timeline_get()["timeline"]
    assert tl["transitions"][a] == "fade"
    assert abs(tl["transition_duration_s"][a] - 8 / 30) < 1e-4
    assert fade_frames(8 / 30) == 8


def test_transition_set_at_s(editor: Editor, media_file: Path) -> None:
    a = _add(editor, media_file, 5.0)
    _add(editor, media_file, 5.0)
    ok = editor.transition_set(at_s=5.0, kind="whip")
    assert ok["ok"] is True
    assert editor.timeline_get()["timeline"]["transitions"][a] == "whip"


def test_transition_budget_warns_over_three(editor: Editor, media_file: Path) -> None:
    ids = [_add(editor, media_file) for _ in range(5)]
    for clip_id, kind in zip(ids[:4], ("fade", "whip", "flash", "match"), strict=True):
        result = editor.transition_set(from_clip_id=clip_id, kind=kind)
        assert result["ok"] is True
    assert any("SPEC-EDIT-13" in w for w in result["warnings"])
    review = editor.review_report()
    assert review["ok"] is False


def test_fade_join_in_assemble_graph(editor: Editor, media_file: Path) -> None:
    a = _add(editor, media_file)
    _add(editor, media_file)
    editor.transition_set(from_clip_id=a, kind="fade")
    store = editor._need()
    cmd = build_assemble_command(
        "ffmpeg",
        store.caption_dir,
        store.project,
        store.timeline,
        editor.media,
        store.output_dir / "out.mp4",
        proxy=True,
        encode_args=["-f", "null", "-"],
        adjustment="",
        overlay_extra=[],
        sfx_files={},
        bed_file=None,
        hero=False,
        preprocessed=False,
        loudnorm=False,
    )
    graph = " ".join(cmd)
    assert "xfade=transition=fade" in graph
    assert "wiperight" not in graph
    assert "wipe" not in whip_filter()


def test_snd12_auto_hold_on_clip_add(tmp_path: Path) -> None:
    runner = FakeRunner(duration_s=3.0, width=1920, height=1080)
    editor = Editor(workspace=tmp_path, runner=runner)
    editor.project_create(name="hold", project_dir=str(tmp_path / "hold"))
    media = touch_media(tmp_path / "src", "short")
    editor.import_file(str(media))
    mid = editor.media[-1].id
    added = editor.clip_add(media_id=mid, duration_s=5.0)
    assert added["ok"] is True
    assert any("SPEC-SND-12" in w and "3.00s source" in w and "5.00s requested" in w for w in added["warnings"])
    clip = editor.timeline_get()["timeline"]["clips"][0]
    assert clip["duration_s"] == 5.0
    assert source_hold_filter(2.0).startswith("tpad=stop_mode=clone")


def test_snd12_auto_hold_on_set_duration(tmp_path: Path) -> None:
    runner = FakeRunner(duration_s=4.0, width=1920, height=1080)
    editor = Editor(workspace=tmp_path, runner=runner)
    editor.project_create(name="hold2", project_dir=str(tmp_path / "hold2"))
    editor.project_set(min_video_duration_s=4.0)
    media = touch_media(tmp_path / "src", "short2")
    editor.import_file(str(media))
    mid = editor.media[-1].id
    editor.clip_add(media_id=mid, duration_s=4.0)
    clip_id = editor.timeline_get()["timeline"]["clips"][0]["id"]
    held = editor.clip_set_duration(clip_id, 6.0)
    assert held["ok"] is True
    assert any("SPEC-SND-12" in w and "4.00s source" in w and "6.00s requested" in w for w in held["warnings"])


def test_snd12_hold_in_clip_intermediate(tmp_path: Path) -> None:
    runner = FakeRunner(duration_s=2.0, width=1920, height=1080)
    editor = Editor(workspace=tmp_path, runner=runner)
    editor.project_create(name="hold3", project_dir=str(tmp_path / "hold3"))
    editor.project_set(min_video_duration_s=2.0)
    media = touch_media(tmp_path / "src", "tiny")
    editor.import_file(str(media))
    mid = editor.media[-1].id
    editor.clip_add(media_id=mid, duration_s=5.0)
    store = editor._need()
    clip = store.timeline.clips[0]
    item = editor.media[0]
    # Drive intermediate so FakeRunner records the ffmpeg argv.
    path = render_clip_intermediate(runner, store, store.project, store.timeline, clip, item, editor.media, preview=True)
    assert path.exists()
    joined = " ".join(" ".join(map(str, call)) for call in runner.calls)
    assert "tpad=stop_mode=clone" in joined
