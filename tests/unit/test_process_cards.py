from __future__ import annotations

from pathlib import Path

from lc_editor.app import Editor
from lc_editor.fonts import display_font, font_label, normalize_font, title_font
from lc_editor.lint.captions import caption_style_warnings
from lc_editor.models import Caption, CaptionWord
from lc_editor.render.captions import drawtext_filter, fontfile_for, karaoke_filters
from lc_editor.render.jobs import prepare_caption_files
from lc_editor.render.textfx import layer_drawtext


PROCESS = "Two-stage foam, then a machine polish"


def _clip(editor: Editor, media_file: Path, duration_s: float = 6.0) -> str:
    editor.import_file(str(media_file))
    editor.clip_add(media_id=editor.media[-1].id, duration_s=duration_s)
    return editor.timeline_get()["timeline"]["clips"][-1]["id"]


def _display_names() -> tuple[str, ...]:
    return ("Clash Display", "Anton")


def test_spec_cap_13_card_is_first_class(editor: Editor, media_file: Path) -> None:
    clip_id = _clip(editor, media_file)
    added = editor.caption_add(clip_id, PROCESS, style="card")
    assert added["ok"] is True
    cap = editor.timeline_get()["timeline"]["captions"][0]
    assert cap["style"] == "card"
    assert cap["font"] == "clash"
    assert len(cap["lines"]) >= 2
    assert cap["lines"][0] != PROCESS or len(PROCESS) <= 26


def test_spec_cap_13_card_filter_has_no_box(editor: Editor, media_file: Path) -> None:
    clip_id = _clip(editor, media_file)
    assert editor.caption_add(clip_id, PROCESS, style="card")["ok"] is True
    store = editor._need()
    tl = prepare_caption_files(store, store.timeline)
    cap = tl.captions[0]
    filt = drawtext_filter(cap, Path(cap.textfile), fontfile_for(cap))
    assert "box=1" not in filt
    assert "box=0" not in filt
    assert "drawbox" not in filt
    assert "boxw=" in filt
    assert "borderw=" in filt
    assert "shadowcolor=" in filt
    face = fontfile_for(cap)
    assert face is not None
    assert font_label(face) in _display_names()
    assert "clash" in face.stem.lower() or "anton" in face.stem.lower()


def test_spec_cap_13_font_clash_without_ffmpeg(editor: Editor, media_file: Path) -> None:
    clip_id = _clip(editor, media_file)
    added = editor.caption_add(clip_id, "Ceramic coat on the hood", font="clash")
    assert added["ok"] is True
    cap = editor.timeline_get()["timeline"]["captions"][0]
    assert cap["font"] == "clash"
    assert cap["style"] == "phrase"
    model = Caption.model_validate(cap)
    assert font_label(fontfile_for(model)) in _display_names()
    bad = editor.caption_add(clip_id, "Next step", font="comic-sans")
    assert bad["ok"] is False
    assert any("unknown font" in w for w in bad["warnings"])


def test_spec_cap_13_project_caption_font(editor: Editor, media_file: Path) -> None:
    clip_id = _clip(editor, media_file)
    set_font = editor.project_set(caption_font="clash")
    assert set_font["ok"] is True
    assert editor.project_get()["project"]["caption_font"] == "clash"
    added = editor.caption_add(clip_id, "Interior vacuum, then dress")
    assert added["ok"] is True
    cap = editor.timeline_get()["timeline"]["captions"][0]
    assert cap["font"] == "clash"
    assert font_label(fontfile_for(Caption.model_validate(cap))) in _display_names()


def test_spec_cap_13_text_style_font(editor: Editor, media_file: Path) -> None:
    editor.import_file(str(media_file))
    editor.clip_add(media_id=editor.media[-1].id, duration_s=3.0)
    added = editor.layer_add(kind="text", text="Before the wash", start_s=0.2, duration_s=2.0)
    assert added["ok"] is True
    layer_id = editor.timeline_get()["timeline"]["layers"][-1]["id"]
    styled = editor.text_style(layer_id, motion="fade", font="clash")
    assert styled["ok"] is True
    layer = editor.timeline_get()["timeline"]["layers"][-1]
    assert layer["style"]["font"] == "clash"
    from lc_editor.models import LayerItem

    filt = layer_drawtext(LayerItem.model_validate(layer), Path("layer.txt"))
    assert "box=1" not in filt
    assert "fontfile=" in filt


def test_spec_cap_13_box_banner_scrim_rejected(editor: Editor, media_file: Path) -> None:
    clip_id = _clip(editor, media_file)
    for kwargs in ({"box": True}, {"background": "blur"}, {"banner": True}, {"scrim": True}):
        result = editor.caption_add(clip_id, PROCESS, style="card", **kwargs)
        assert result["ok"] is False
        blob = " ".join(result["warnings"])
        assert "SPEC-CRAFT-02" in blob or "SPEC-CAP-04" in blob
    assert editor.timeline_get()["timeline"]["captions"] == []


def test_spec_cap_13_lint_warns_karaoke_on_process_line(editor: Editor, media_file: Path) -> None:
    clip_id = _clip(editor, media_file)
    words = [
        {"text": w, "start_s": i * 0.3, "end_s": i * 0.3 + 0.25}
        for i, w in enumerate(PROCESS.split())
    ]
    added = editor.caption_add(clip_id, PROCESS, style="karaoke", words=words)
    assert added["ok"] is True
    lint = editor.caption_lint()
    blob = " ".join(lint.get("warnings", []))
    assert "SPEC-CAP-13" in blob
    assert lint["ok"] is True
    cards = lint.get("cards") or []
    assert cards
    assert cards[0]["style"] == "karaoke"


def test_spec_cap_13_pop_and_karaoke_still_work(editor: Editor, media_file: Path) -> None:
    clip_id = _clip(editor, media_file)
    pop = editor.caption_add(
        clip_id,
        "I need this",
        style="pop",
        words=[
            {"text": "I", "start_s": 0.1, "end_s": 0.28},
            {"text": "need", "start_s": 0.28, "end_s": 0.50},
            {"text": "this", "start_s": 0.50, "end_s": 0.72},
        ],
    )
    assert pop["ok"] is True
    karaoke = editor.caption_add(
        clip_id,
        "born working vibe",
        style="karaoke",
        words=[
            {"text": "born", "start_s": 0.2, "end_s": 0.7},
            {"text": "working", "start_s": 0.7, "end_s": 1.3},
            {"text": "vibe", "start_s": 1.3, "end_s": 1.9},
        ],
    )
    assert karaoke["ok"] is True
    caps = editor.timeline_get()["timeline"]["captions"]
    assert [c["style"] for c in caps] == ["pop", "karaoke"]
    lint = editor.caption_lint()
    assert not any("SPEC-CAP-13" in w for w in lint.get("warnings", []))


def test_spec_cap_13_karaoke_filters_stay_box_free() -> None:
    words = [
        CaptionWord(text="born", start_s=0.2, end_s=0.7),
        CaptionWord(text="working", start_s=0.7, end_s=1.3),
    ]
    cap = Caption(id="t1", clip_id="c1", text="born working", style="karaoke", role="title", words=words)
    filt = ",".join(karaoke_filters(cap, [Path("w0.txt"), Path("w1.txt")], fontfile_for(cap)))
    assert "box=1" not in filt
    assert "0xFFE14A" in filt


def test_spec_cap_13_pop_long_phrase_warns() -> None:
    cap = Caption(
        id="t1",
        clip_id="c1",
        text=PROCESS,
        style="pop",
        words=[CaptionWord(text=PROCESS, start_s=0.0, end_s=1.2)],
    )
    warns = caption_style_warnings(cap)
    assert any("SPEC-CAP-13" in w for w in warns)


def test_spec_cap_13_named_font_aliases() -> None:
    assert normalize_font("Clash Display") == "clash-display"
    assert normalize_font("clash") == "clash"
    assert display_font() == title_font()
    assert font_label(title_font()) in _display_names()


def test_spec_cap_13_default_phrase_has_no_box(editor: Editor, media_file: Path) -> None:
    clip_id = _clip(editor, media_file)
    added = editor.caption_add(clip_id, "Interior vacuum, then dress")
    assert added["ok"] is True
    cap = editor.timeline_get()["timeline"]["captions"][0]
    assert cap["style"] == "phrase"
    store = editor._need()
    tl = prepare_caption_files(store, store.timeline)
    filt = drawtext_filter(tl.captions[0], Path(tl.captions[0].textfile), fontfile_for(tl.captions[0]))
    assert "box=1" not in filt
