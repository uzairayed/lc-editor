from __future__ import annotations

from pathlib import Path

from lc_editor.app import Editor
from lc_editor.models import Caption
from lc_editor.render import captions as captions_mod
from lc_editor.render.captions import drawtext_filter
from lc_editor.render.jobs import prepare_caption_files


WORDS = [
    {"text": "born", "start_s": 0.2, "end_s": 0.7},
    {"text": "working", "start_s": 0.7, "end_s": 1.3},
    {"text": "vibe", "start_s": 1.3, "end_s": 1.9},
]


def _clip(editor: Editor, media_file: Path, duration_s: float = 5.0) -> str:
    editor.import_file(str(media_file))
    editor.clip_add(media_id=editor.media[-1].id, duration_s=duration_s)
    return editor.timeline_get()["timeline"]["clips"][-1]["id"]


def test_spec_cap_05_default_is_not_karaoke(editor: Editor, media_file: Path) -> None:
    clip_id = _clip(editor, media_file)
    added = editor.caption_add(clip_id, "Cafe Imran stop")
    assert added["ok"] is True
    cap = editor.timeline_get()["timeline"]["captions"][0]
    assert cap.get("style", "phrase") == "phrase"


def test_spec_cap_10_karaoke_opt_in(editor: Editor, media_file: Path) -> None:
    clip_id = _clip(editor, media_file)
    added = editor.caption_add(clip_id, "born working vibe", style="karaoke", words=WORDS)
    assert added["ok"] is True
    cap = editor.timeline_get()["timeline"]["captions"][0]
    assert cap["style"] == "karaoke"
    assert cap["words"][0]["text"] == "born"
    assert cap["role"] == "title"


def test_spec_cap_10_karaoke_needs_words(editor: Editor, media_file: Path) -> None:
    clip_id = _clip(editor, media_file)
    missing = editor.caption_add(clip_id, "born working vibe", style="karaoke")
    assert missing["ok"] is False


def test_spec_cap_10_karaoke_graph_highlights_spoken_word(tmp_path: Path) -> None:
    Word = getattr(__import__("lc_editor.models", fromlist=["CaptionWord"]), "CaptionWord", None)
    karaoke_filters = getattr(captions_mod, "karaoke_filters", None)
    assert Word is not None
    assert callable(karaoke_filters)
    cap = Caption(
        id="t1",
        clip_id="c1",
        text="born working vibe",
        role="title",
        style="karaoke",
        words=[Word(text="born", start_s=0.2, end_s=0.7), Word(text="working", start_s=0.7, end_s=1.3)],
        textfile=str(tmp_path / "c.txt"),
    )
    (tmp_path / "c.txt").write_text("born working vibe", encoding="utf-8")
    word_files = [tmp_path / "w0.txt", tmp_path / "w1.txt"]
    word_files[0].write_text("born", encoding="utf-8")
    word_files[1].write_text("working", encoding="utf-8")
    filt = ",".join(karaoke_filters(cap, word_files, None))
    assert "0xFFE14A" in filt
    assert "0xF6EBD4" in filt
    assert "box=1" not in filt
    assert "born" not in filt.replace("textfile", "")
    assert "n/3" not in filt or "karaoke" in cap.style


def test_spec_cap_10_karaoke_apostrophe_stays_in_file(editor: Editor, media_file: Path) -> None:
    clip_id = _clip(editor, media_file)
    words = [
        {"text": "don't", "start_s": 0.1, "end_s": 0.6},
        {"text": "stop", "start_s": 0.6, "end_s": 1.1},
    ]
    added = editor.caption_add(clip_id, "don't stop", style="karaoke", words=words)
    assert added["ok"] is True
    store = editor._need()
    tl = prepare_caption_files(store, store.timeline)
    cap = tl.captions[0]
    body = Path(cap.textfile).read_text(encoding="utf-8")
    assert "don't" in body
    filt = drawtext_filter(cap, Path(cap.textfile), None)
    assert "don't" not in filt
    assert "box=1" not in filt
