from __future__ import annotations

from pathlib import Path

from lc_editor.app import Editor
from lc_editor.lint.captions import hold_s, wrap_text


TEXT_44 = "xxxxxxxxxxxxxxxxxxxxxxxxx yyyyyyyyyyyyyyyyyy"


def _long_clip(editor: Editor, media_file: Path, duration_s: float = 5.0) -> str:
    editor.import_file(str(media_file))
    editor.clip_add(media_id=editor.media[-1].id, duration_s=duration_s)
    return editor.timeline_get()["timeline"]["clips"][-1]["id"]


def test_spec_cap_01_one_line_floor() -> None:
    text = "100 km down the N-5"
    assert len(text) == 19
    assert hold_s(text, wrap_text(text)) == 1.50


def test_spec_cap_02_one_line_target() -> None:
    text = "2 hours, one fuel stop"
    assert len(text) == 22
    assert hold_s(text, wrap_text(text)) == 1.62


def test_spec_cap_03_two_line_readability() -> None:
    assert len(TEXT_44) == 44
    lines = wrap_text(TEXT_44)
    assert len(lines) == 2
    assert hold_s(TEXT_44, lines) == 2.84


def test_spec_cap_04_two_line_floor() -> None:
    text = "Cafe Imran, Gharo"
    lines = ["Cafe Imran,", "Gharo"]
    assert hold_s(text, lines) == 1.80


def test_spec_cap_05_three_line_explainer_ok(editor: Editor, media_file: Path) -> None:
    clip_id = _long_clip(editor, media_file)
    text = "600-year-old city of tombs, 2 hours from Karachi"
    assert len(text) == 48
    lines = wrap_text(text)
    assert len(lines) == 3
    result = editor.caption_add(clip_id, text)
    assert result["ok"] is True
    cap = editor.timeline_get()["timeline"]["captions"][0]
    assert len(cap["lines"]) == 3
    assert cap["hold_s"] >= 1.80


def test_spec_cap_05_wrap_rejects_four_lines(editor: Editor, media_file: Path) -> None:
    clip_id = _long_clip(editor, media_file)
    text = "alpha bravo charlie delta echo foxtrot golf hotel india juliet kilo lima mike november oscar"
    assert len(wrap_text(text)) > 3
    result = editor.caption_add(clip_id, text)
    assert result["ok"] is False
    assert any("SPEC-CAP-02" in w for w in result["warnings"])


def test_spec_cap_05_twenty_six_chars_one_line(editor: Editor, media_file: Path) -> None:
    clip_id = _long_clip(editor, media_file)
    text = "600-year-old city of tombs"
    assert len(text) == 26
    result = editor.caption_add(clip_id, text)
    assert result["ok"] is True
    cap = editor.timeline_get()["timeline"]["captions"][0]
    assert cap["lines"] == [text]


def test_spec_cap_06_seventeen_words(editor: Editor, media_file: Path) -> None:
    clip_id = _long_clip(editor, media_file)
    bad = editor.caption_add(
        clip_id,
        "one two three four five six seven eight nine ten eleven twelve thirteen fourteen fifteen sixteen seventeen",
    )
    assert bad["ok"] is False
    assert any("SPEC-CAP-02" in w for w in bad["warnings"])
    good = editor.caption_add(clip_id, "2 hours, one fuel stop")
    assert good["ok"] is True


def test_spec_cap_07_box_rejected(editor: Editor, media_file: Path) -> None:
    clip_id = _long_clip(editor, media_file)
    result = editor.caption_add(clip_id, "Cafe Imran, Gharo", box=True)
    assert result["ok"] is False
    assert any("SPEC-CRAFT-02" in w for w in result["warnings"])
    assert editor.timeline_get()["timeline"]["captions"] == []


def test_spec_cap_09_safe_zone(editor: Editor, media_file: Path) -> None:
    clip_id = _long_clip(editor, media_file)
    bad = editor.caption_add(clip_id, "Cafe Imran, Gharo", y_pct=0.8)
    assert bad["ok"] is False
    good = editor.caption_add(clip_id, "Cafe Imran, Gharo", y_pct=0.36)
    assert good["ok"] is True


def test_spec_cap_11_short_clip_rejected(editor: Editor, media_file: Path) -> None:
    editor.import_file(str(media_file))
    editor.clip_add(media_id=editor.media[-1].id, duration_s=1.2)
    clip_id = editor.timeline_get()["timeline"]["clips"][-1]["id"]
    result = editor.caption_add(clip_id, "100 km down the N-5")
    assert result["ok"] is False
    assert any("SPEC-CAP-02" in w for w in result["warnings"])


def test_spec_cap_03_via_mcp(editor: Editor, media_file: Path) -> None:
    clip_id = _long_clip(editor, media_file, 5.0)
    result = editor.caption_add(clip_id, TEXT_44)
    assert result["ok"] is True
    cap = editor.timeline_get()["timeline"]["captions"][0]
    assert cap["hold_s"] == 2.84


def test_spec_cap_12_lint_does_not_mutate(editor: Editor, media_file: Path) -> None:
    clip_id = _long_clip(editor, media_file)
    editor.caption_add(clip_id, "Cafe Imran, Gharo")
    version = editor.timeline_get()["timeline_summary"]["version"]
    lint = editor.caption_lint()
    assert lint["ok"] is True
    assert editor.timeline_get()["timeline_summary"]["version"] == version
