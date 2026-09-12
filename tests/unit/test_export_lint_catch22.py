from __future__ import annotations

from pathlib import Path

from lc_editor.app import Editor
from lc_editor.lint import captions as capmod
from lc_editor.render.runner import FakeRunner
from tests.conftest import touch_media


def test_process_still_ack_and_craft_no_longer_fight(editor: Editor, tmp_path: Path) -> None:
    still = touch_media(tmp_path / "src", "card", ".jpg")
    editor.import_file(str(still))
    editor.clip_add(media_id=editor.media[-1].id, duration_s=2.2)
    clip = editor.store.timeline.clips[0]
    editor.store.timeline = editor.store.timeline.model_copy(
        update={"clips": [clip.model_copy(update={"motion": "none", "is_still": True, "duration_s": 2.2})]}
    )
    result = editor.review_report()
    assert result["ok"] is True
    assert any("SPEC-CRAFT-05" in w for w in result["warnings"])
    assert not any("SPEC-EDIT-ACK-01" in e for e in result["errors"])
    assert not any("SPEC-CRAFT-05" in e for e in result["errors"])


def test_soft_512_fit_blur_never_blocks_export(tmp_path: Path) -> None:
    runner = FakeRunner(duration_s=5.0, width=512, height=288)
    editor = Editor(workspace=tmp_path, runner=runner)
    editor.project_create(name="detail", project_dir=str(tmp_path / "detail"))
    soft = touch_media(tmp_path / "src", "wash", ".jpg")
    editor.import_file(str(soft))
    mid = editor.media[-1].id
    editor.media_tag(mid, role="wash")
    editor.clip_add(media_id=mid, duration_s=5.0)
    clip_id = editor.timeline_get()["timeline"]["clips"][0]["id"]
    assert editor.clip_set_fit(clip_id, "fit_blur")["ok"] is True
    result = editor.review_report()
    assert result["ok"] is True, result
    assert any("SPEC-QLT-01" in w for w in result["warnings"])
    assert not any("cover-upscales" in e for e in result["errors"])
    assert editor.export()["ok"] is True


def test_cap06_lenient_warns_strict_blocks(editor: Editor, tmp_path: Path, monkeypatch) -> None:
    still = touch_media(tmp_path / "src", "photo", ".jpg")
    editor.import_file(str(still))
    editor.clip_add(media_id=editor.media[-1].id, duration_s=5.0)
    clip_id = editor.timeline_get()["timeline"]["clips"][0]["id"]
    assert editor.caption_add(clip_id, "Soft mitt pass")["ok"] is True
    monkeypatch.setattr(capmod, "sample_underlay_luma", lambda *_a, **_k: 0.85)

    lenient = editor.review_report()
    assert lenient["ok"] is True
    assert any("SPEC-CAP-06" in w for w in lenient["warnings"])
    assert not any("SPEC-CAP-06" in e for e in lenient["errors"])

    assert editor.project_set(caption_contrast="strict")["ok"] is True
    strict = editor.review_report()
    assert strict["ok"] is False
    assert any("SPEC-CAP-06" in e for e in strict["errors"])
