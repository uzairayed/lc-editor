from __future__ import annotations

from pathlib import Path

from lc_editor.app import Editor


def _clip(editor: Editor, media_file: Path) -> str:
    editor.import_file(str(media_file))
    editor.clip_add(media_id=editor.media[-1].id, duration_s=5.0)
    return editor.timeline_get()["timeline"]["clips"][-1]["id"]


def test_spec_snd_01_music_rejected(editor: Editor, media_file: Path) -> None:
    _clip(editor, media_file)
    bed = editor.audio_bed("cinematic")
    assert bed["ok"] is False
    place = editor.sfx_place("music", at_s=0.0)
    assert place["ok"] is False
    assert any("SPEC-SND-01" in w for w in place["warnings"])
    assert editor.timeline_get()["timeline"]["sfx"] == []


REEL_SFX = (
    "sparkle",
    "swipe",
    "bubble",
    "button",
    "paper",
    "cash",
    "click",
    "correct",
    "success",
)


def test_spec_snd_02_manifest_has_no_music(editor: Editor) -> None:
    listed = editor.sfx_list()
    kinds = {i["kind"] for i in listed["sfx"]}
    assert "tick" in kinds and "whoosh" in kinds and "riser" in kinds
    assert "music" not in kinds
    assert "drum_loop" not in kinds


def test_spec_snd_02_reel_pack_kinds(editor: Editor) -> None:
    listed = editor.sfx_list()
    items = {i["kind"]: i for i in listed["sfx"]}
    for kind in REEL_SFX:
        assert kind in items
        assert items[kind]["file"] == f"{kind}.wav"
        assert items[kind]["duration_s"] > 0
        assert str(items[kind].get("license") or "").strip()
        blob = " ".join(str(v) for v in items[kind].values()).lower()
        assert "capcut" not in blob
        assert "222764" not in blob
        assert "1184192" not in blob
    assert editor.sfx_place("cash", at_s=0.0, gain_db=-12.0)["ok"] is True


def test_spec_snd_02_place_reel_kinds(editor: Editor, media_file: Path) -> None:
    _clip(editor, media_file)
    for kind in REEL_SFX:
        placed = editor.sfx_place(kind, at_s=0.4, gain_db=-12.0)
        assert placed["ok"] is True, placed
    kinds = [s["kind"] for s in editor.timeline_get()["timeline"]["sfx"]]
    assert set(REEL_SFX) <= set(kinds)


def test_spec_snd_02_empty_license_warns(editor: Editor, media_file: Path) -> None:
    _clip(editor, media_file)
    dest = editor.store.user_sfx_dir / "scratch.wav"
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(b"RIFF" + b"\x00" * 40)
    placed = editor.sfx_place("scratch", at_s=0.0, gain_db=-12.0)
    assert placed["ok"] is True
    review = editor.review_report()
    assert any("SPEC-SND-02" in w and "license" in w.lower() for w in review["warnings"])


def test_spec_snd_02_zoom_auto_is_opt_in(editor: Editor, media_file: Path) -> None:
    clip_id = _clip(editor, media_file)
    editor.motion_zoom_in(clip_id)
    assert editor.timeline_get()["timeline"]["sfx"] == []
    first = editor.sfx_zoom_auto()
    second = editor.sfx_zoom_auto()
    assert first["ok"] is True
    swipes = [s for s in editor.timeline_get()["timeline"]["sfx"] if s["kind"] == "swipe"]
    assert len(swipes) == 1
    assert second["ok"] is True
    assert len([s for s in editor.timeline_get()["timeline"]["sfx"] if s["kind"] == "swipe"]) == 1


def test_spec_snd_03_caption_auto_idempotent(editor: Editor, media_file: Path) -> None:
    clip_id = _clip(editor, media_file)
    editor.caption_add(clip_id, "Cafe Imran, Gharo")
    first = editor.sfx_caption_auto()
    second = editor.sfx_caption_auto()
    assert first["ok"] is True
    ticks = [s for s in editor.timeline_get()["timeline"]["sfx"] if s["kind"] == "tick"]
    assert len(ticks) == 1
    assert second["ok"] is True
    assert len([s for s in editor.timeline_get()["timeline"]["sfx"] if s["kind"] == "tick"]) == 1


def test_spec_snd_04_whoosh_on_decorated_only(editor: Editor, media_file: Path) -> None:
    a = _clip(editor, media_file)
    editor.clip_add(media_id=editor.media[-1].id, duration_s=2.0)
    editor.transition_set(a, "whip")
    editor.sfx_transition_auto()
    editor.sfx_transition_auto()
    whooshes = [s for s in editor.timeline_get()["timeline"]["sfx"] if s["kind"] == "whoosh"]
    assert len(whooshes) == 1


def test_spec_snd_05_sfx_under_bed(editor: Editor, media_file: Path) -> None:
    _clip(editor, media_file)
    editor.audio_bed("wind", gain_db=-6.0)
    hot = editor.sfx_place("tick", at_s=0.0, gain_db=-8.0)
    assert hot["ok"] is False
    ok = editor.sfx_place("tick", at_s=0.0, gain_db=-12.0)
    assert ok["ok"] is True


def test_spec_snd_06_highpass(editor: Editor, media_file: Path) -> None:
    _clip(editor, media_file)
    bad = editor.audio_highpass(0)
    assert bad["ok"] is False
    good = editor.audio_highpass(100)
    assert good["ok"] is True
    assert editor.timeline_get()["timeline"]["highpass_hz"] == 100


def test_spec_snd_09_mix_true_peak(editor: Editor, media_file: Path) -> None:
    _clip(editor, media_file)
    editor.audio_bed("wind", gain_db=0.0)
    editor.sfx_place("whoosh", at_s=1.0, gain_db=-6.0)
    mix = editor.mix_preview()
    assert "true_peak_dbtp" in mix
