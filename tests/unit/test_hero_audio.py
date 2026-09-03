from __future__ import annotations

from pathlib import Path

from lc_editor.app import Editor
from lc_editor.models import Clip, MediaItem, Project, Timeline
from lc_editor.render.audio import loudnorm_hero
from lc_editor.render.compositor import build_assemble_command
from lc_editor.render.graph import hero_encode_args, hero_encode_legal
from lc_editor.render.jobs import AssembleError, render_clip_intermediate


def test_spec_snd_16_live_intermediate_maps_aac_48k(editor, media_file: Path) -> None:
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
    assert last[last.index("-ar") + 1] == "48000"
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


def test_spec_snd_17_hero_encode_is_aac_48k(tmp_path: Path) -> None:
    args = hero_encode_args(tmp_path / "reel.mp4")
    assert args[args.index("-c:a") + 1] == "aac"
    assert args[args.index("-ar") + 1] == "48000"
    assert args[args.index("-ac") + 1] == "2"
    assert hero_encode_legal(args) is True
    no_rate = [a for a in args if a not in ("-ar", "48000")]
    # drop the value paired with -ar already removed; ensure missing rate fails
    stripped = []
    skip = False
    for a in args:
        if skip:
            skip = False
            continue
        if a == "-ar":
            skip = True
            continue
        stripped.append(a)
    assert hero_encode_legal(stripped) is False


def test_spec_snd_17_loudnorm_cinema_vs_speech() -> None:
    cinema = loudnorm_hero()
    speech = loudnorm_hero("speech")
    assert "I=-16" in cinema
    assert "LRA=8" in cinema
    assert "I=-14" in speech
    assert "LRA=11" in speech
    assert "aresample=48000" in cinema
    assert "aresample=48000" in speech


def test_spec_snd_17_assemble_speech_loudnorm(editor: Editor, media_file: Path) -> None:
    editor.import_file(str(media_file))
    editor.clip_add(media_id=editor.media[-1].id, duration_s=2.5)
    editor.project_set(loudnorm="speech")
    assert editor.review_report()["ok"] is True
    assert editor.export()["ok"] is True
    assemble = None
    for args in editor.runner.calls:
        out = (args[-1] if args else "").replace("\\", "/")
        if out.endswith("/reel.mp4") and "-filter_complex" in args:
            assemble = args
    assert assemble is not None
    graph = assemble[assemble.index("-filter_complex") + 1]
    assert "loudnorm=I=-14" in graph
    assert "aresample=48000" in graph
    assert assemble[assemble.index("-ar") + 1] == "48000"


def test_spec_snd_17_karachi_keeps_cinema_loudnorm() -> None:
    project = Project(id="p", name="n", preset="karachi")
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
        encode_args=hero_encode_args(Path("/tmp/reel.mp4")),
        adjustment="",
        overlay_extra=[],
        sfx_files={},
        bed_file=None,
        hero=True,
        preprocessed=True,
        loudnorm=True,
    )
    graph = cmd[cmd.index("-filter_complex") + 1]
    assert "I=-16" in graph
    assert "aresample=48000" in graph
