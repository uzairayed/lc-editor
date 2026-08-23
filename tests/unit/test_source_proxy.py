from __future__ import annotations

from pathlib import Path

from lc_editor.app import Editor
from lc_editor.models import SOURCE_PROXY_H, SOURCE_PROXY_W
from lc_editor.render.jobs import source_proxy_args, source_proxy_vf


def test_source_proxy_args_are_cheap() -> None:
    args = source_proxy_args("ffmpeg", "in.mp4", "out.mp4", kind="video")
    blob = " ".join(args)
    assert f"{SOURCE_PROXY_W}:{SOURCE_PROXY_H}" in blob
    assert "lut3d" not in blob
    assert "afftdn" not in blob
    assert "agate" not in blob
    assert "noautorotate" not in blob
    assert args[args.index("-i") + 1] == "in.mp4"
    assert "-ss" not in args


def test_source_proxy_stills_seek_after_input() -> None:
    args = source_proxy_args("ffmpeg", "in.jpg", "out.mp4", kind="image", duration_s=2.5)
    assert args.index("-i") < args.index("in.jpg") or args[args.index("-i") + 1] == "in.jpg"
    ss = args.index("-ss") if "-ss" in args else -1
    inp = args.index("-i")
    assert ss == -1 or ss > inp
    assert "lut3d" not in " ".join(args)
    assert source_proxy_vf().startswith("scale=360:640")


def test_import_writes_cached_source_proxy(editor: Editor, media_file: Path) -> None:
    first = editor.import_file(str(media_file))
    item = first["media"]
    assert item["proxy_path"]
    proxy = Path(item["proxy_path"])
    assert proxy.exists()
    again = editor.media_proxy(item["id"])
    assert again["ok"] is True
    assert again["cached"] == [True]
    assert again["paths"][0] == item["proxy_path"]


def test_preview_proxy_skips_hero_lut_and_denoise(editor: Editor, media_file: Path) -> None:
    editor.import_file(str(media_file))
    editor.clip_add(media_id=editor.media[-1].id, duration_s=2.0)
    editor.audio_denoise("all", "outdoor")
    editor.grade_preset("winter_trip")
    result = editor.preview_proxy()
    assert result["ok"] is True
    clip_blob = " ".join(
        " ".join(c) for c in editor.runner.calls if c and "/clips/" in c[-1].replace("\\", "/")
    )
    proxy_blob = " ".join(
        " ".join(c) for c in editor.runner.calls if any("/proxies/" in a.replace("\\", "/") for a in c)
    )
    assemble_blob = " ".join(
        " ".join(c)
        for c in editor.runner.calls
        if "-filter_complex" in c and any("preview_proxy" in a.replace("\\", "/") for a in c)
    )
    assert "lut3d" not in clip_blob
    assert "lut3d" not in proxy_blob
    assert "afftdn" not in clip_blob
    assert "afftdn" not in assemble_blob
    assert "lut3d" in assemble_blob
