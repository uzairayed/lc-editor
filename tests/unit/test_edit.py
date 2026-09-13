from __future__ import annotations

from pathlib import Path

from lc_editor.app import Editor
from lc_editor.models import (
    DURATION_CAP_S,
    DURATION_SOFT_MAX_S,
    Project,
    resolved_duration_cap_s,
    resolved_duration_soft_max_s,
)
from tests.conftest import touch_media


def _add(editor: Editor, media_file: Path, duration_s: float = 2.0) -> str:
    editor.import_file(str(media_file))
    mid = editor.media[-1].id
    editor.clip_add(media_id=mid, duration_s=duration_s)
    return editor.timeline_get()["timeline"]["clips"][-1]["id"]


def test_spec_edit_01_no_gaps(editor: Editor, media_file: Path) -> None:
    _add(editor, media_file, 2.0)
    _add(editor, media_file, 3.0)
    _add(editor, media_file, 1.5)
    clips = editor.timeline_get()["timeline"]["clips"]
    assert clips[0]["start_s"] == 0.0
    assert clips[1]["start_s"] == 2.0
    assert clips[2]["start_s"] == 5.0


def test_spec_edit_02_clip_add_appends(editor: Editor, media_file: Path) -> None:
    _add(editor, media_file, 2.0)
    _add(editor, media_file, 3.0)
    result = editor.clip_add(media_id=editor.media[-1].id, duration_s=1.5)
    assert result["ok"] is True
    assert result["timeline_summary"]["duration_s"] == 6.5
    assert editor.timeline_get()["timeline"]["clips"][-1]["start_s"] == 5.0


def test_spec_edit_03_remove_closes_hole(editor: Editor, media_file: Path) -> None:
    a = _add(editor, media_file, 2.0)
    b = _add(editor, media_file, 3.0)
    _add(editor, media_file, 1.0)
    editor.clip_remove(b)
    clips = editor.timeline_get()["timeline"]["clips"]
    assert [c["id"] for c in clips][0] == a
    assert clips[1]["start_s"] == 2.0
    assert editor.timeline_get()["timeline_summary"]["duration_s"] == 3.0


def test_spec_edit_04_reorder(editor: Editor, media_file: Path) -> None:
    _add(editor, media_file, 2.0)
    _add(editor, media_file, 3.0)
    c = _add(editor, media_file, 1.0)
    editor.clip_reorder(c, 0)
    clips = editor.timeline_get()["timeline"]["clips"]
    assert [round(c["start_s"], 2) for c in clips] == [0.0, 1.0, 3.0]
    assert clips[0]["id"] == c


def test_spec_edit_06_ripple_trim(editor: Editor, media_file: Path) -> None:
    _add(editor, media_file, 2.0)
    b = _add(editor, media_file, 3.0)
    _add(editor, media_file, 4.0)
    result = editor.clip_ripple_trim(b, edge="out", delta_s=-1.0)
    assert result["ok"] is True
    clips = editor.timeline_get()["timeline"]["clips"]
    assert clips[1]["duration_s"] == 2.0
    assert clips[2]["start_s"] == 4.0
    assert result["timeline_summary"]["duration_s"] == 8.0


def test_spec_edit_07_split(editor: Editor, media_file: Path) -> None:
    clip_id = _add(editor, media_file, 5.0)
    # trim to 6s source is 5s; use 5s and split at 2
    editor.clip_trim(clip_id, 0.0, 5.0)
    editor.clip_split(clip_id, 2.0)
    clips = editor.timeline_get()["timeline"]["clips"]
    assert len(clips) == 2
    assert clips[0]["duration_s"] == 2.0
    assert clips[1]["duration_s"] == 3.0
    assert clips[0]["out_s"] == clips[1]["in_s"]


def test_spec_edit_10_refocus_rejects_range(editor: Editor, media_file: Path) -> None:
    clip_id = _add(editor, media_file)
    bad = editor.clip_refocus(clip_id, x=1.5, y=0.5)
    assert bad["ok"] is False
    good = editor.clip_refocus(clip_id, x=0.4, y=0.3)
    assert good["ok"] is True
    clip = editor.timeline_get()["timeline"]["clips"][0]
    assert clip["focus_x"] == 0.4
    assert clip["focus_y"] == 0.3


def test_spec_edit_13_banned_wipe(editor: Editor, media_file: Path) -> None:
    clip_id = _add(editor, media_file)
    result = editor.transition_set(clip_id, "wiperight")
    assert result["ok"] is False
    assert any("SPEC-EDIT-13" in w for w in result["warnings"])


def test_spec_edit_13_close_fade_last_only(editor: Editor, media_file: Path) -> None:
    a = _add(editor, media_file)
    _add(editor, media_file)
    bad = editor.transition_set(a, "close_fade")
    assert bad["ok"] is False
    last = editor.timeline_get()["timeline"]["clips"][-1]["id"]
    good = editor.transition_set(last, "close_fade")
    assert good["ok"] is True


def test_spec_edit_14_duration_cap(editor: Editor, media_file: Path) -> None:
    editor.import_file(str(media_file))
    mid = editor.media[-1].id
    for _ in range(30):
        editor.clip_add(media_id=mid, duration_s=2.0)
    assert editor.timeline_get()["timeline_summary"]["duration_s"] == 60.0
    rejected = editor.clip_add(media_id=mid, duration_s=2.0)
    assert rejected["ok"] is False
    assert any("SPEC-EDIT-14" in w for w in rejected["warnings"])
    assert editor.timeline_get()["timeline_summary"]["duration_s"] == 60.0


def test_resolved_duration_cap_defaults() -> None:
    assert resolved_duration_cap_s(None) == DURATION_CAP_S
    assert resolved_duration_cap_s(Project(id="p", name="r", duration_cap_s=0)) == DURATION_CAP_S
    assert resolved_duration_cap_s(Project(id="p", name="r", duration_cap_s=180)) == 180.0


def test_resolved_duration_soft_max_respects_raised_cap() -> None:
    assert resolved_duration_soft_max_s(None) == DURATION_SOFT_MAX_S
    assert resolved_duration_soft_max_s(Project(id="p", name="r")) == DURATION_SOFT_MAX_S
    assert resolved_duration_soft_max_s(Project(id="p", name="r", duration_cap_s=180)) == 180.0
    assert resolved_duration_soft_max_s(Project(id="p", name="r", duration_cap_s=20)) == DURATION_SOFT_MAX_S


def test_spec_edit_14_project_set_duration_cap(editor: Editor) -> None:
    assert editor.project_get()["project"]["duration_cap_s"] == 60.0
    raised = editor.project_set(duration_cap_s=180)
    assert raised["ok"] is True
    assert editor.project_get()["project"]["duration_cap_s"] == 180.0
    omitted = editor.project_set(name="reel")
    assert omitted["ok"] is True
    assert editor.project_get()["project"]["duration_cap_s"] == 180.0
    reset = editor.project_set(duration_cap_s=0)
    assert reset["ok"] is True
    assert editor.project_get()["project"]["duration_cap_s"] == 60.0
    bad_neg = editor.project_set(duration_cap_s=-1)
    assert bad_neg["ok"] is False
    assert any("SPEC-EDIT-14" in w for w in bad_neg["warnings"])
    bad_max = editor.project_set(duration_cap_s=601)
    assert bad_max["ok"] is False
    assert any("SPEC-EDIT-14" in w for w in bad_max["warnings"])
    assert editor.project_get()["project"]["duration_cap_s"] == 60.0


def test_spec_edit_14_raised_cap_allows_process_length(editor: Editor, media_file: Path) -> None:
    editor.import_file(str(media_file))
    mid = editor.media[-1].id
    assert editor.project_set(duration_cap_s=180)["ok"] is True
    last = None
    for _ in range(26):
        last = editor.clip_add(media_id=mid, duration_s=5.0)
        assert last["ok"] is True
    assert last["timeline_summary"]["duration_s"] == 130.0
    assert any("SPEC-EDIT-15" in w and "60.00s default" in w for w in last["warnings"])
    assert not any("over 28.00s target" in w for w in last["warnings"])
    assert not any("SPEC-EDIT-14" in w for w in last["warnings"])
    for _ in range(10):
        last = editor.clip_add(media_id=mid, duration_s=5.0)
        assert last["ok"] is True
    assert last["timeline_summary"]["duration_s"] == 180.0
    rejected = editor.clip_add(media_id=mid, duration_s=5.0)
    assert rejected["ok"] is False
    assert any("SPEC-EDIT-14" in w and "180.00s" in w for w in rejected["warnings"])
    assert editor.timeline_get()["timeline_summary"]["duration_s"] == 180.0


def test_spec_edit_15_soft_warning_over_28(editor: Editor, media_file: Path) -> None:
    editor.import_file(str(media_file))
    mid = editor.media[-1].id
    for _ in range(15):
        result = editor.clip_add(media_id=mid, duration_s=2.0)
    assert result["ok"] is True
    assert result["timeline_summary"]["duration_s"] == 30.0
    assert any("SPEC-EDIT-15" in w and "over 28.00s target" in w for w in result["warnings"])


def test_spec_edit_15_raised_cap_skips_28s_target_warning(editor: Editor, media_file: Path) -> None:
    editor.import_file(str(media_file))
    mid = editor.media[-1].id
    assert editor.project_set(duration_cap_s=180)["ok"] is True
    for _ in range(8):
        result = editor.clip_add(media_id=mid, duration_s=5.0)
        assert result["ok"] is True
    assert result["timeline_summary"]["duration_s"] == 40.0
    assert not any("over 28.00s target" in w for w in result["warnings"])
    assert not any("SPEC-EDIT-15" in w for w in result["warnings"])
    review = editor.review_report()
    assert review["ok"] is True
    assert review["report"]["in_target_length"] is True
    assert not any("over 28.00s target" in w for w in review["warnings"])


def test_spec_edit_16_op_id_idempotent(editor: Editor, media_file: Path) -> None:
    editor.import_file(str(media_file))
    mid = editor.media[-1].id
    first = editor.clip_add(media_id=mid, duration_s=2.0, op_id="a1")
    second = editor.clip_add(media_id=mid, duration_s=2.0, op_id="a1")
    assert first == second
    assert editor.timeline_get()["timeline_summary"]["clip_count"] == 1


def test_spec_edit_17_undo_redo(editor: Editor, media_file: Path) -> None:
    _add(editor, media_file, 2.0)
    _add(editor, media_file, 2.0)
    assert editor.timeline_get()["timeline_summary"]["clip_count"] == 2
    editor.undo()
    assert editor.timeline_get()["timeline_summary"]["clip_count"] == 1
    editor.redo()
    assert editor.timeline_get()["timeline_summary"]["clip_count"] == 2
    editor.undo()
    _add(editor, media_file, 2.0)
    redone = editor.redo()
    assert redone["ok"] is False


def test_spec_edit_12_zoom_in_out(editor: Editor, media_file: Path) -> None:
    _add(editor, media_file, 2.4)
    clip_id = editor.timeline_get()["timeline"]["clips"][-1]["id"]
    zoomed = editor.motion_zoom_in(clip_id)
    assert zoomed["ok"] is True
    clip = editor.timeline_get()["timeline"]["clips"][-1]
    assert clip["motion"] == "zoom_in"
    assert clip["zoom_frames"] == 27
    assert clip["zoom_amount"] == 1.10
    out = editor.motion_zoom_out(clip_id, frames=30, amount=1.12)
    assert out["ok"] is True
    clip = editor.timeline_get()["timeline"]["clips"][-1]
    assert clip["motion"] == "zoom_out"
    assert clip["zoom_frames"] == 30
    assert clip["zoom_amount"] == 1.12
    bad = editor.motion_zoom_in(clip_id, frames=4)
    assert bad["ok"] is False


def test_spec_edit_18_still_is_clip(editor: Editor, tmp_path: Path) -> None:
    still = touch_media(tmp_path / "src", "photo", ".jpg")
    editor.import_file(str(still))
    editor.clip_add(media_id=editor.media[-1].id)
    clip = editor.timeline_get()["timeline"]["clips"][-1]
    assert clip["is_still"] is True
    assert clip["motion"] == "kenburns"
    assert clip["duration_s"] == 2.5


def test_spec_edit_19_timeline_get_one_call(editor: Editor, media_file: Path) -> None:
    _add(editor, media_file)
    got = editor.timeline_get()
    assert "timeline" in got
    assert got["timeline"]["clips"]
    assert "timeline_summary" in got
