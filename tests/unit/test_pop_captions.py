from __future__ import annotations

from pathlib import Path

from lc_editor.app import Editor
from lc_editor.models import Caption, CaptionWord
from lc_editor.render import captions as captions_mod
from lc_editor.render.graph import clip_hash_payload, clip_video_filters
from lc_editor.render.jobs import prepare_caption_files
from lc_editor.models import Clip, MediaItem, Project


WORDS = [
    {"text": "I", "start_s": 0.10, "end_s": 0.28},
    {"text": "need", "start_s": 0.28, "end_s": 0.50},
    {"text": "this", "start_s": 0.50, "end_s": 0.72},
]


def _clip(editor: Editor, media_file: Path, duration_s: float = 8.0) -> str:
    editor.import_file(str(media_file))
    editor.clip_add(media_id=editor.media[-1].id, duration_s=duration_s)
    return editor.timeline_get()["timeline"]["clips"][-1]["id"]


def test_spec_cap_11_pop_is_opt_in(editor: Editor, media_file: Path) -> None:
    clip_id = _clip(editor, media_file)
    added = editor.caption_add(clip_id, "Cafe Imran stop")
    assert added["ok"] is True
    cap = editor.timeline_get()["timeline"]["captions"][0]
    assert cap.get("style", "phrase") == "phrase"


def test_spec_cap_11_pop_needs_words(editor: Editor, media_file: Path) -> None:
    clip_id = _clip(editor, media_file)
    missing = editor.caption_add(clip_id, "I need this", style="pop")
    assert missing["ok"] is False
    assert any("SPEC-CAP-11" in w for w in missing["warnings"])


def test_spec_cap_11_pop_one_word_at_a_time(editor: Editor, media_file: Path) -> None:
    clip_id = _clip(editor, media_file)
    added = editor.caption_add(clip_id, "I need this", style="pop", words=WORDS)
    assert added["ok"] is True
    cap = editor.timeline_get()["timeline"]["captions"][0]
    assert cap["style"] == "pop"
    assert [w["text"] for w in cap["words"]] == ["I", "need", "this"]
    assert cap["words"][0]["start_s"] == 0.10


def test_spec_cap_11_pop_skips_hold_floor(editor: Editor, media_file: Path) -> None:
    clip_id = _clip(editor, media_file, duration_s=1.2)
    words = [{"text": "go", "start_s": 0.0, "end_s": 0.20}]
    added = editor.caption_add(clip_id, "go", style="pop", words=words)
    assert added["ok"] is True
    lint = editor.caption_lint()
    assert not any("hold" in w.lower() for w in lint.get("errors", []) + lint.get("warnings", []))


def test_spec_cap_11_pop_accepts_a_hundred_whisper_words(editor: Editor, media_file: Path) -> None:
    clip_id = _clip(editor, media_file, duration_s=8.0)
    words = [{"text": f"w{i}", "start_s": i * 0.05, "end_s": i * 0.05 + 0.04} for i in range(120)]
    added = editor.caption_add(clip_id, " ".join(w["text"] for w in words), style="pop", words=words)
    assert added["ok"] is True
    cap = editor.timeline_get()["timeline"]["captions"][0]
    assert len(cap["words"]) == 120


def test_spec_cap_11_pop_expands_contractions(editor: Editor, media_file: Path) -> None:
    clip_id = _clip(editor, media_file)
    added = editor.caption_add(
        clip_id,
        "I'm here",
        style="pop",
        words=[
            {"text": "I'm", "start_s": 0.1, "end_s": 0.5},
            {"text": "here", "start_s": 0.5, "end_s": 0.9},
        ],
    )
    assert added["ok"] is True
    texts = [w["text"] for w in editor.timeline_get()["timeline"]["captions"][0]["words"]]
    assert "I'm" not in texts
    assert "I" in texts
    assert "am" in texts
    assert "here" in texts


def test_spec_cap_11_pop_renders_one_ass_not_drawtext_chain(tmp_path: Path) -> None:
    ass_body = getattr(captions_mod, "pop_ass_body", None)
    assert callable(ass_body)
    words = [
        CaptionWord(id="w0", text="need", start_s=0.0, end_s=0.3),
        CaptionWord(id="w1", text="homeless", start_s=0.3, end_s=0.7),
    ]
    cap = Caption(id="t1", clip_id="c1", text="need homeless", style="pop", words=words, y_pct=0.36)
    body = ass_body(cap, clip_start_s=0.0)
    assert "Dialogue:" in body
    assert body.count("Dialogue:") == 2
    assert "need" in body
    assert "homeless" in body
    assert "0xFFE14A" in body or "A4E1FF" in body or "4AE1FF" in body
    assert "Alignment" in body
    assert "\\fscx128" in body or "fscx128" in body
    assert "drawtext" not in body
    assert "box=1" not in body
    assert "'" not in body.split("[Events]")[-1].replace("Dialogue:", "")


def test_spec_cap_11_pop_stays_off_clip_intermediate(tmp_path: Path) -> None:
    cap = Caption(
        id="t1",
        clip_id="c1",
        text="need this",
        style="pop",
        words=[CaptionWord(text="need", start_s=0.0, end_s=0.2)],
        textfile=str(tmp_path / "c.txt"),
    )
    clip = Clip(id="c1", media_id="m1")
    media = MediaItem(id="m1", path="x.mp4", original_path="x.mp4", width=1920, height=1080)
    filt = clip_video_filters(clip, media, [cap], Project(id="p", name="n"))
    assert "drawtext" not in filt
    a = clip_hash_payload(clip, [cap], Project(id="p", name="n"))
    b = clip_hash_payload(clip, [], Project(id="p", name="n"))
    assert a == b


def test_spec_cap_11_export_uses_one_ass_overlay(editor: Editor, media_file: Path) -> None:
    clip_id = _clip(editor, media_file)
    words = [{"text": f"w{i}", "start_s": i * 0.04, "end_s": i * 0.04 + 0.03} for i in range(80)]
    assert editor.caption_add(clip_id, "talk", style="pop", words=words)["ok"] is True
    assert editor.review_report()["ok"] is True
    assert editor.export()["ok"] is True
    assemble = None
    for args in editor.runner.calls:
        out = (args[-1] if args else "").replace("\\", "/")
        if out.endswith("/reel.mp4") and "-filter_complex" in args:
            assemble = args
    assert assemble is not None
    graph = assemble[assemble.index("-filter_complex") + 1]
    assert "ass=" in graph
    assert graph.count("drawtext=") < 8


def test_spec_cap_11_prepare_writes_ass(editor: Editor, media_file: Path) -> None:
    clip_id = _clip(editor, media_file)
    editor.caption_add(clip_id, "I need this", style="pop", words=WORDS)
    store = editor._need()
    tl = prepare_caption_files(store, store.timeline)
    cap = tl.captions[0]
    ass = Path(cap.textfile).with_suffix(".ass")
    assert ass.exists()
    text = ass.read_text(encoding="utf-8")
    assert "Dialogue:" in text
    assert "I'm" not in text
