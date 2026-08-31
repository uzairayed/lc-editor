from __future__ import annotations

from pathlib import Path

from lc_editor.app import Editor
from tests.conftest import touch_media


def test_spec_ses_08_eleven_call_session(editor: Editor, tmp_path: Path) -> None:
    inbox = tmp_path / "inbox"
    for i in range(14):
        touch_media(inbox, f"shot{i:02d}")

    created = editor.project_get()
    assert created["project"]["aspect"] == "9:16"
    brief = editor.project_set(subject="demo reel", target_duration_s=22.0, caption_mode="sparse")
    assert brief["ok"] is True

    imported = editor.import_folder(str(inbox))
    assert imported["ok"] is True
    assert len(imported["media"]) == 14

    analyzed = editor.media_analyze()
    assert analyzed["ok"] is True
    ranked = editor.shots_rank("hook", top_k=5)
    assert ranked["ok"] is True
    assert ranked["shots"]

    sheet = editor.contact_sheet()
    assert sheet["ok"] is True

    ids = []
    for item in editor.media_list()["media"][:6]:
        add = editor.clip_add(media_id=item["id"], duration_s=3.8)
        assert add["ok"] is True
        ids.append(editor.timeline_get()["timeline"]["clips"][-1]["id"])
    assert 6 <= len(ids) <= 8

    for clip_id in ids[:3]:
        assert editor.clip_refocus(clip_id, 0.45, 0.35)["ok"] is True

    for clip_id in ids[:4]:
        assert editor.motion_kenburns(clip_id)["ok"] is True

    captions = [
        "Hook in one line",
        "Second beat",
        "What it does",
        "The detail",
        "Save this",
    ]
    for clip_id, text in zip(ids[:5], captions):
        added = editor.caption_add(clip_id, text)
        assert added["ok"] is True, added

    assert editor.audio_bed("room")["ok"] is True
    assert editor.sfx_caption_auto()["ok"] is True
    assert editor.sfx_place("button", at_s=4.0, gain_db=-12.0)["ok"] is True
    assert editor.sfx_place("whoosh", at_s=12.0, gain_db=-12.0)["ok"] is True

    assert editor.grade_preset("neutral")["ok"] is True
    assert editor.overlay_preview("ig")["ok"] is True

    stills = editor.preview_stills()
    proxy = editor.preview_proxy()
    assert stills["ok"] and proxy["ok"]

    recut = editor.clip_trim(ids[-1], 0.0, 2.4)
    assert recut["ok"] is True
    review = editor.review_report()
    assert review["ok"] is True
    exported = editor.export()
    assert exported["ok"] is True
    assert Path(exported["hero"]).exists()
    assert Path(exported["proxy"]).exists()
