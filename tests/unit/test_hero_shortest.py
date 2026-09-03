from __future__ import annotations

from pathlib import Path

from lc_editor.app import Editor
from lc_editor.models import Clip, MediaItem, Project, Timeline
from lc_editor.render import graph as graph_mod
from lc_editor.render.compositor import build_assemble_command
from lc_editor.render.graph import hero_encode_args, hero_encode_legal
from lc_editor.render.jobs import render_clip_intermediate


def test_spec_export_08_hero_args_reject_shortest(tmp_path: Path) -> None:
    args = hero_encode_args(tmp_path / "reel.mp4")
    assert "-shortest" not in args
    assert hero_encode_legal(args) is True
    banned = [*args[:-1], "-shortest", str(tmp_path / "reel.mp4")]
    assert hero_encode_legal(banned) is False


def test_spec_export_08_assemble_hero_omits_shortest(editor: Editor, media_file: Path) -> None:
    editor.import_file(str(media_file))
    editor.clip_add(media_id=editor.media[-1].id, duration_s=2.5)
    assert editor.review_report()["ok"] is True
    assert editor.export()["ok"] is True
    assemble = None
    for args in editor.runner.calls:
        out = (args[-1] if args else "").replace("\\", "/")
        if out.endswith("/reel.mp4") and "-filter_complex" in args:
            assemble = args
    assert assemble is not None
    assert "-shortest" not in assemble
    assert "-t" in assemble


def test_spec_export_08_clip_hero_intermediate_omits_shortest(editor, media_file: Path) -> None:
    editor.import_file(str(media_file))
    item = editor.media[0]
    clip = Clip(id="c1", media_id=item.id, duration_s=3.0, in_s=0.0, out_s=3.0, muted=True)
    timeline = Timeline(clips=[clip])
    render_clip_intermediate(
        editor.runner, editor.store, editor.store.project, timeline, clip, item, [item], preview=False
    )
    last = editor.runner.calls[-1]
    assert "-shortest" not in last


def test_spec_export_08_legal_on_full_assemble_command(tmp_path: Path) -> None:
    legal = getattr(graph_mod, "hero_encode_legal", None)
    assert callable(legal)
    dest = tmp_path / "reel.mp4"
    cmd = [
        "ffmpeg",
        "-y",
        "-i",
        "a.mp4",
        "-filter_complex",
        "[0:v]copy[vout];[0:a]anull[aout]",
        "-map",
        "[vout]",
        "-map",
        "[aout]",
        "-shortest",
        *hero_encode_args(dest),
    ]
    assert legal(cmd) is False
    cmd_ok = [a for a in cmd if a != "-shortest"]
    assert legal(cmd_ok) is True


def test_spec_snd_12_assemble_pins_timeline_duration() -> None:
    project = Project(id="p", name="n")
    timeline = Timeline(clips=[Clip(id="c1", media_id="m1", duration_s=2.5)])
    items = [MediaItem(id="m1", path="x.mp4", original_path="x.mp4", kind="video", has_audio=True)]
    cmd = build_assemble_command(
        "ffmpeg",
        Path("/tmp"),
        project,
        timeline,
        items,
        Path("/tmp/reel.mp4"),
        proxy=False,
        encode_args=["-t", "2.5000", *hero_encode_args(Path("/tmp/reel.mp4"))],
        adjustment="",
        overlay_extra=[],
        sfx_files={},
        bed_file=None,
        hero=True,
        preprocessed=True,
        loudnorm=True,
    )
    assert "-shortest" not in cmd
    assert cmd[cmd.index("-t") + 1] == "2.5000"
