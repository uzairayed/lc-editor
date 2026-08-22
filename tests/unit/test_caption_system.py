from __future__ import annotations

from pathlib import Path

from lc_editor.app import Editor
from lc_editor.lint.captions import hold_s, wrap_text
from lc_editor.models import Caption
from lc_editor.render.captions import drawtext_filter
from lc_editor.render.jobs import overlay_filters
from lc_editor.models import OverlayFlags, Project


def _long_clip(editor: Editor, media_file: Path, duration_s: float = 5.0) -> str:
    editor.import_file(str(media_file))
    editor.clip_add(media_id=editor.media[-1].id, duration_s=duration_s)
    return editor.timeline_get()["timeline"]["clips"][-1]["id"]


def test_spec_cap_02_forty_chars_two_line_floor() -> None:
    text = "xxxxxxxxxxxxxxxxxxxxxxxxx yyyyyyyyyyyyyy"
    assert len(text) == 40
    lines = wrap_text(text)
    assert len(lines) == 2
    assert hold_s(text, lines) >= 1.80
    assert hold_s(text, lines) == 2.62


def test_spec_cap_04_all_caps_rejected(editor: Editor, media_file: Path) -> None:
    clip_id = _long_clip(editor, media_file)
    result = editor.caption_add(clip_id, "CAFE IMRAN GHARO NOW")
    assert result["ok"] is False
    assert any("SPEC-CAP-04" in w for w in result["warnings"])
    assert "box" not in " ".join(result["warnings"]).lower() or "never" in " ".join(result["warnings"]).lower()


def test_spec_cap_05_punch_enter_in_graph(tmp_path: Path) -> None:
    cap = Caption(
        id="t1",
        clip_id="c1",
        text="Cafe Imran, Gharo",
        role="title",
        enter="punch",
        textfile=str(tmp_path / "c.txt"),
    )
    (tmp_path / "c.txt").write_text("Cafe Imran, Gharo", encoding="utf-8")
    filt = drawtext_filter(cap, tmp_path / "c.txt", None)
    assert "n/3" in filt or "min(1" in filt
    assert "box=1" not in filt
    assert "0xF6EBD4" in filt


def test_spec_cap_03_overlay_guides() -> None:
    project = Project(id="p", name="n", overlays=OverlayFlags(preview_guides=True, preview_platform="tt"))
    filters = overlay_filters(project, for_preview=True)
    blob = ",".join(filters)
    assert "0.22" in blob
    assert "0.50" in blob
    assert "853" in blob
    assert "227" in blob


def test_spec_cap_08_lint_structured_phone_proof(editor: Editor, media_file: Path) -> None:
    clip_id = _long_clip(editor, media_file)
    added = editor.caption_add(clip_id, "600-year-old city of tombs")
    assert added["ok"] is True
    lint = editor.caption_lint()
    assert "hold_s" in lint
    assert lint["hold_s"] >= 1.8
    assert lint["bbox"] is not None
    assert lint["bbox"]["y"] >= 270
    assert lint["bbox"]["y2"] <= 1248
    assert lint["bbox"]["cx"] == 540
    assert "contrast" in lint
    proof = Path(lint["phone_proof"])
    assert proof.exists()
    assert proof.stat().st_size > 2000
    assert editor.timeline_get()["timeline_summary"]["version"] == added["timeline_summary"]["version"]


def test_spec_cap_01_title_default_enter(editor: Editor, media_file: Path) -> None:
    clip_id = _long_clip(editor, media_file)
    editor.caption_add(clip_id, "Cafe Imran", role="title")
    cap = editor.timeline_get()["timeline"]["captions"][0]
    assert cap["role"] == "title"
    assert cap["enter"] == "punch"
