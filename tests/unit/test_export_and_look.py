from __future__ import annotations

from pathlib import Path

from lc_editor.app import Editor
from lc_editor.render.graph import hero_encode_args, hero_encode_legal, proxy_encode_args, share_encode_args


def test_spec_export_01_hero_args(tmp_path: Path) -> None:
    args = hero_encode_args(tmp_path / "reel.mp4")
    assert "libx264" in args
    assert "yuv420p" in args
    assert "1080x1920" in args
    assert "aac" in args
    wide = hero_encode_args(tmp_path / "demo.mp4", 1920, 1080)
    assert "1920x1080" in wide
    assert hero_encode_legal(wide) is True
    assert "+faststart" in args
    assert "30" in args


def test_spec_export_10_share_args(tmp_path: Path) -> None:
    args = share_encode_args(tmp_path / "reel_share.mp4")
    assert "720x1280" in args
    assert args[args.index("-crf") + 1] == "22"
    assert args[args.index("-b:a") + 1] == "128k"
    assert "+faststart" in args
    assert "yuv420p" in args
    assert args[args.index("-color_range") + 1] == "tv"
    assert hero_encode_legal(args) is False
    wide = share_encode_args(tmp_path / "wide.mp4", 1920, 1080)
    assert "1280x720" in wide


def test_spec_export_02_proxy_args(tmp_path: Path) -> None:
    args = proxy_encode_args(tmp_path / "p.mp4")
    assert args[args.index("-preset") + 1] == "veryfast"
    assert args[args.index("-crf") + 1] == "30"
    assert "540x960" in args


def test_spec_export_03_export_gated(editor: Editor, media_file: Path) -> None:
    editor.import_file(str(media_file))
    editor.clip_add(media_id=editor.media[-1].id)
    blocked = editor.export()
    assert blocked["ok"] is False
    assert any("SPEC-EXPORT-03" in w for w in blocked["warnings"])
    review = editor.review_report()
    assert review["ok"] is True
    assert review["report"]["grade"] == "neutral"
    out = editor.export()
    assert out["ok"] is True
    assert Path(out["hero"]).exists()
    assert Path(out["proxy"]).exists()


def test_spec_export_03_gate_recloses(editor: Editor, media_file: Path) -> None:
    editor.import_file(str(media_file))
    editor.clip_add(media_id=editor.media[-1].id)
    editor.review_report()
    editor.clip_add(media_id=editor.media[-1].id)
    blocked = editor.export()
    assert blocked["ok"] is False


def test_spec_export_06_export_op_id(editor: Editor, media_file: Path) -> None:
    editor.import_file(str(media_file))
    editor.clip_add(media_id=editor.media[-1].id)
    editor.review_report()
    first = editor.export(op_id="exp1")
    second = editor.export(op_id="exp1")
    assert first == second


def test_spec_rnd_07_one_grade(editor: Editor) -> None:
    editor.grade_preset("motovlog")
    editor.grade_preset("winter_trip")
    assert editor.project_get()["project"]["grade_preset"] == "winter_trip"


def test_spec_rnd_08_protect(editor: Editor, media_file: Path) -> None:
    editor.import_file(str(media_file))
    editor.clip_add(media_id=editor.media[-1].id)
    clip_id = editor.timeline_get()["timeline"]["clips"][0]["id"]
    result = editor.grade_protect(clip_id, True)
    assert result["ok"] is True
    clip = editor.timeline_get()["timeline"]["clips"][0]
    assert clip["protect"] is True
    assert clip["grade_intensity"] == 0.40


def test_spec_rnd_09_overlays_off_by_default(editor: Editor) -> None:
    overlays = editor.project_get()["project"]["overlays"]
    assert overlays["social_chrome"] is False
    assert overlays["series_card"] is False
    editor.overlay_preview("ig")
    assert editor.project_get()["project"]["overlays"]["preview_platform"] == "ig"
    editor.overlay_bake("progress", True)
    assert editor.project_get()["project"]["overlays"]["progress"] is True


def test_spec_rnd_11_preview_stills(editor: Editor, media_file: Path) -> None:
    editor.import_file(str(media_file))
    editor.clip_add(media_id=editor.media[-1].id)
    stills = editor.preview_stills()
    assert stills["ok"] is True
    assert stills["paths"]
    path = Path(stills["paths"][0])
    assert path.is_absolute()
    assert path.exists()
    assert path.stat().st_size > 0
    assert "base64" not in stills
    sheet = editor.contact_sheet()
    assert Path(sheet["path"]).is_absolute()
    assert Path(sheet["path"]).exists()
    assert "base64" not in sheet
