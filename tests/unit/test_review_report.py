from __future__ import annotations

from pathlib import Path

from lc_editor.app import Editor
from lc_editor.models import Caption, SfxPlacement
from tests.conftest import touch_media


def _video_clip(editor: Editor, media_file: Path) -> str:
    editor.import_file(str(media_file))
    editor.clip_add(media_id=editor.media[-1].id, duration_s=2.0)
    return editor.timeline_get()["timeline"]["clips"][-1]["id"]


def test_review_fails_locked_still_over_1_4s(editor: Editor, tmp_path: Path) -> None:
    still = touch_media(tmp_path / "src", "photo", ".jpg")
    editor.import_file(str(still))
    editor.clip_add(media_id=editor.media[-1].id, duration_s=2.5)
    clip = editor.store.timeline.clips[0]
    editor.store.timeline = editor.store.timeline.model_copy(
        update={"clips": [clip.model_copy(update={"motion": "none", "is_still": True, "duration_s": 2.0})]}
    )
    result = editor.review_report()
    assert result["ok"] is False
    assert any("SPEC-CRAFT-05" in w for w in result["warnings"])
    assert editor.store.project.reviewed_version is None


def test_review_fails_caption_safe_zone(editor: Editor, media_file: Path) -> None:
    clip_id = _video_clip(editor, media_file)
    cap = Caption(id="t1", clip_id=clip_id, text="Cafe Imran, Gharo", y_pct=0.8, lines=["Cafe Imran, Gharo"], hold_s=1.5)
    editor.store.timeline = editor.store.timeline.model_copy(update={"captions": [cap]})
    result = editor.review_report()
    assert result["ok"] is False
    assert any("SPEC-CAP-03" in w for w in result["warnings"])


def test_review_fails_hold_too_short(editor: Editor, media_file: Path) -> None:
    editor.import_file(str(media_file))
    editor.clip_add(media_id=editor.media[-1].id, duration_s=1.2)
    clip_id = editor.timeline_get()["timeline"]["clips"][-1]["id"]
    cap = Caption(id="t1", clip_id=clip_id, text="100 km down the N-5", y_pct=0.36, lines=["100 km down the N-5"], hold_s=1.5)
    editor.store.timeline = editor.store.timeline.model_copy(update={"captions": [cap]})
    result = editor.review_report()
    assert result["ok"] is False
    assert any("SPEC-CAP-02" in w for w in result["warnings"])


def test_review_fails_music_flag(editor: Editor, media_file: Path) -> None:
    _video_clip(editor, media_file)
    editor.store.project = editor.store.project.model_copy(update={"allow_music": True})
    result = editor.review_report()
    assert result["ok"] is False
    assert any("SPEC-CRAFT-01" in w for w in result["warnings"])


def test_review_fails_sfx_above_bed(editor: Editor, media_file: Path) -> None:
    _video_clip(editor, media_file)
    editor.audio_bed("wind", gain_db=-6.0)
    hot = SfxPlacement(id="s1", kind="tick", at_s=0.0, gain_db=-8.0)
    editor.store.timeline = editor.store.timeline.model_copy(update={"sfx": [hot]})
    result = editor.review_report()
    assert result["ok"] is False
    assert any("SPEC-SND-05" in w for w in result["warnings"])


def test_review_fails_over_60s(editor: Editor, media_file: Path) -> None:
    _video_clip(editor, media_file)
    clip = editor.store.timeline.clips[0]
    editor.store.timeline = editor.store.timeline.model_copy(
        update={"clips": [clip.model_copy(update={"duration_s": 61.0})]}
    )
    result = editor.review_report()
    assert result["ok"] is False
    assert any("SPEC-EDIT-14" in w for w in result["warnings"])


def test_review_ok_unlocks_export(editor: Editor, media_file: Path) -> None:
    _video_clip(editor, media_file)
    review = editor.review_report()
    assert review["ok"] is True
    assert review["report"]["errors"] == []
    exported = editor.export()
    assert exported["ok"] is True
    sidecar = Path(exported["sidecar"])
    assert sidecar.exists()
    data = sidecar.read_text(encoding="utf-8")
    assert "shots" in data
    assert "duration_s" in data
    assert "grade" in data
    replay = editor.export(op_id="exp-side")
    again = editor.export(op_id="exp-side")
    assert replay["sidecar"] == again["sidecar"]
