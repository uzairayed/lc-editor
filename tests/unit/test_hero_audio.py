from __future__ import annotations

from pathlib import Path

from lc_editor.app import Editor
from lc_editor.models import Clip, Timeline
from lc_editor.render.jobs import AssembleError, render_clip_intermediate


def test_spec_snd_16_live_intermediate_maps_audio(editor, media_file: Path) -> None:
    editor.import_file(str(media_file))
    item = editor.media[0]
    clip = Clip(id="c1", media_id=item.id, duration_s=3.0, in_s=0.0, out_s=3.0)
    timeline = Timeline(clips=[clip])
    render_clip_intermediate(
        editor.runner, editor.store, editor.store.project, timeline, clip, item, [item], preview=False
    )
    last = editor.runner.calls[-1]
    blob = " ".join(last)
    assert "0:a" in blob or "0:a" in last
    assert "apad" in blob
    assert "atrim" in blob
    assert last[last.index("-c:a") + 1] == "aac"
    assert "-an" not in last


def test_spec_snd_16_three_clips_from_one_source_each_have_audio(editor: Editor, media_file: Path) -> None:
    editor.import_file(str(media_file))
    mid = editor.media[-1].id
    editor.clip_add(media_id=mid, in_s=0.0, duration_s=2.5)
    editor.clip_add(media_id=mid, in_s=1.0, duration_s=2.5)
    editor.clip_add(media_id=mid, in_s=2.0, duration_s=2.5)
    assert editor.review_report(allow_dense=True)["ok"] is True
    assert editor.export()["ok"] is True
    assemble = None
    clip_cmds = []
    for args in editor.runner.calls:
        out = (args[-1] if args else "").replace("\\", "/")
        if "-an" in args:
            continue
        if "cache/clips" in out and out.endswith(".mp4"):
            clip_cmds.append(args)
        if out.endswith("/reel.mp4") and "-filter_complex" in args:
            assemble = args
    assert assemble is not None
    graph = assemble[assemble.index("-filter_complex") + 1]
    assert "[0:a]" in graph
    assert "[1:a]" in graph
    assert "[2:a]" in graph
    for cmd in clip_cmds:
        assert "-an" not in cmd
        blob = " ".join(cmd)
        assert "0:a" in blob or "anullsrc" in blob


def test_spec_snd_16_assemble_fails_closed_without_audio() -> None:
    from lc_editor.render.jobs import require_clip_audio

    try:
        require_clip_audio({"has_audio": False}, "c1")
        raise AssertionError("expected AssembleError")
    except AssembleError as exc:
        assert "c1" in str(exc)
        assert "no audio" in str(exc).lower()
