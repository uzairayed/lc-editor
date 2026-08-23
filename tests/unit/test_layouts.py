from __future__ import annotations

from pathlib import Path

from lc_editor.app import Editor
from lc_editor.models import Clip, LayoutPane, MediaItem, Project
from lc_editor.ops.layouts import parse_panes
from lc_editor.ops.timeline import Reject
from lc_editor.render.graph import clip_hash_payload
from lc_editor.render.layouts import layout_cells, layout_filter_complex, stack_join
from lc_editor.render.motion import crop_cover
from tests.conftest import touch_media


def _import_two(editor: Editor, media_file: Path) -> tuple[str, str]:
    editor.import_file(str(media_file))
    a = editor.media[-1].id
    editor.import_file(str(media_file))
    b = editor.media[-1].id
    return a, b


def test_layout_add_stack_v_is_one_clip(editor: Editor, media_file: Path) -> None:
    a, b = _import_two(editor, media_file)
    result = editor.layout_add(
        kind="stack_v",
        panes=[{"media_id": a, "in_s": 0.2}, {"media_id": b, "focus_y": 0.4}],
        duration_s=3.0,
    )
    assert result["ok"] is True
    assert result["timeline_summary"]["clip_count"] == 1
    assert result["timeline_summary"]["duration_s"] == 3.0
    clip = editor.timeline_get()["timeline"]["clips"][0]
    assert clip["layout"] == "stack_v"
    assert clip["media_id"] == a
    assert clip["in_s"] == 0.2
    assert len(clip["panes"]) == 2
    assert clip["panes"][1]["focus_y"] == 0.4
    assert clip["start_s"] == 0.0


def test_layout_add_wrong_count_rejected(editor: Editor, media_file: Path) -> None:
    a, _b = _import_two(editor, media_file)
    bad = editor.layout_add(kind="stack_v", panes=[{"media_id": a}])
    assert bad["ok"] is False
    assert any("SPEC-LAYO-01" in w for w in bad["warnings"])
    assert editor.timeline_get()["timeline_summary"]["clip_count"] == 0


def test_layout_add_unknown_kind_rejected(editor: Editor, media_file: Path) -> None:
    a, b = _import_two(editor, media_file)
    bad = editor.layout_add(kind="pip", panes=[{"media_id": a}, {"media_id": b}])
    assert bad["ok"] is False
    assert any("SPEC-LAYO-01" in w for w in bad["warnings"])


def test_layout_counts_as_one_for_density(editor: Editor, media_file: Path) -> None:
    editor.import_file(str(media_file))
    mid = editor.media[-1].id
    editor.clip_add(media_id=mid, duration_s=2.4)
    editor.layout_add(
        kind="stack_v",
        panes=[{"media_id": mid}, {"media_id": mid}],
        duration_s=2.4,
    )
    assert editor.timeline_get()["timeline_summary"]["clip_count"] == 2
    assert editor.timeline_get()["timeline"]["clips"][1]["start_s"] == 2.4


def test_clip_split_rejected_on_layout(editor: Editor, media_file: Path) -> None:
    a, b = _import_two(editor, media_file)
    editor.layout_add(kind="stack_v", panes=[{"media_id": a}, {"media_id": b}], duration_s=4.0)
    clip_id = editor.timeline_get()["timeline"]["clips"][0]["id"]
    bad = editor.clip_split(clip_id, 2.0)
    assert bad["ok"] is False
    assert any("SPEC-LAYO-06" in w for w in bad["warnings"])
    assert editor.timeline_get()["timeline_summary"]["clip_count"] == 1


def test_layout_pane_and_refocus(editor: Editor, media_file: Path) -> None:
    a, b = _import_two(editor, media_file)
    editor.layout_add(kind="stack_v", panes=[{"media_id": a}, {"media_id": b}], duration_s=2.5)
    clip_id = editor.timeline_get()["timeline"]["clips"][0]["id"]
    moved = editor.layout_pane(clip_id, 1, focus_x=0.7, focus_y=0.3)
    assert moved["ok"] is True
    clip = editor.timeline_get()["timeline"]["clips"][0]
    assert clip["panes"][1]["focus_x"] == 0.7
    assert clip["focus_x"] == 0.5
    editor.clip_refocus(clip_id, 0.2, 0.8)
    clip = editor.timeline_get()["timeline"]["clips"][0]
    assert clip["focus_x"] == 0.2
    assert clip["panes"][0]["focus_x"] == 0.2
    assert clip["panes"][1]["focus_x"] == 0.7


def test_layout_clear_flattens(editor: Editor, media_file: Path) -> None:
    a, b = _import_two(editor, media_file)
    editor.layout_add(kind="stack_v", panes=[{"media_id": a}, {"media_id": b}], duration_s=2.5)
    clip_id = editor.timeline_get()["timeline"]["clips"][0]["id"]
    cleared = editor.layout_clear(clip_id)
    assert cleared["ok"] is True
    clip = editor.timeline_get()["timeline"]["clips"][0]
    assert clip["layout"] is None
    assert clip["panes"] == []
    assert clip["media_id"] == a


def test_layout_update_kind(editor: Editor, media_file: Path) -> None:
    a, b = _import_two(editor, media_file)
    editor.layout_add(kind="stack_v", panes=[{"media_id": a}, {"media_id": b}], duration_s=2.5)
    clip_id = editor.timeline_get()["timeline"]["clips"][0]["id"]
    changed = editor.layout_update(clip_id, kind="stack_h")
    assert changed["ok"] is True
    assert editor.timeline_get()["timeline"]["clips"][0]["layout"] == "stack_h"


def test_review_fails_missing_pane_media(editor: Editor, media_file: Path) -> None:
    a, b = _import_two(editor, media_file)
    editor.layout_add(kind="stack_v", panes=[{"media_id": a}, {"media_id": b}], duration_s=2.5)
    clip = editor.store.timeline.clips[0]
    broken = clip.model_copy(update={"panes": [clip.panes[0], clip.panes[1].model_copy(update={"media_id": "gone"})]})
    editor.store.timeline = editor.store.timeline.model_copy(update={"clips": [broken]})
    result = editor.review_report()
    assert result["ok"] is False
    assert any("SPEC-LAYO-05" in w for w in result["warnings"])


def test_media_remove_rejects_pane_use(editor: Editor, media_file: Path) -> None:
    a, b = _import_two(editor, media_file)
    editor.layout_add(kind="stack_v", panes=[{"media_id": a}, {"media_id": b}], duration_s=2.5)
    blocked = editor.media_remove(b)
    assert blocked["ok"] is False


def test_preview_stills_uses_vstack(editor: Editor, media_file: Path) -> None:
    a, b = _import_two(editor, media_file)
    editor.layout_add(kind="stack_v", panes=[{"media_id": a}, {"media_id": b}], duration_s=2.5)
    stills = editor.preview_stills()
    assert stills["ok"] is True
    assert stills["paths"]
    joined = " ".join(" ".join(call) for call in editor.runner.calls)
    assert "vstack" in joined


def test_parse_panes_accepts_json_string() -> None:
    panes = parse_panes('[{"media_id": "m1"}, {"media_id": "m2", "in_s": 1}]')
    assert len(panes) == 2
    assert panes[1].in_s == 1.0
    try:
        parse_panes("not-json")
        raise AssertionError("expected reject")
    except Reject:
        pass


def test_layout_hash_includes_panes() -> None:
    project = Project(id="p", name="n")
    a = Clip(id="c1", media_id="m1", layout="stack_v", panes=[LayoutPane(media_id="m1"), LayoutPane(media_id="m2")])
    b = Clip(id="c1", media_id="m1", layout="stack_v", panes=[LayoutPane(media_id="m1"), LayoutPane(media_id="m3")])
    assert clip_hash_payload(a, [], project) != clip_hash_payload(b, [], project)


def test_crop_cover_and_stack_graph() -> None:
    cover = crop_cover(1920, 1080, 1080, 960, 0.5, 0.5)
    assert cover.startswith("crop=")
    assert "scale=1080:960" in cover
    assert layout_cells("stack_v")[0] == (0, 0, 1080, 960)
    clip = Clip(
        id="c1",
        media_id="m1",
        layout="stack_v",
        duration_s=2.5,
        panes=[LayoutPane(media_id="m1"), LayoutPane(media_id="m2")],
    )
    items = [
        MediaItem(id="m1", path="a.mp4", original_path="a.mp4", width=1920, height=1080),
        MediaItem(id="m2", path="b.mp4", original_path="b.mp4", width=1920, height=1080),
    ]
    graph = layout_filter_complex(clip, items)
    assert "vstack=inputs=2[laid]" in graph
    assert stack_join("grid_2x2", ["[p0]", "[p1]", "[p2]", "[p3]"]).count("hstack") == 2


def test_layout_list(editor: Editor) -> None:
    result = editor.layout_list()
    assert result["ok"] is True
    kinds = {row["kind"] for row in result["layouts"]}
    assert kinds == {"stack_v", "stack_h", "stack_v3", "grid_2x2"}


def test_all_still_layout_gets_kenburns(editor: Editor, tmp_path: Path) -> None:
    still = touch_media(tmp_path / "src", "wall", ".jpg")
    editor.import_file(str(still))
    mid = editor.media[-1].id
    editor.layout_add(kind="stack_v", panes=[{"media_id": mid}, {"media_id": mid}], duration_s=2.5)
    clip = editor.timeline_get()["timeline"]["clips"][0]
    assert clip["is_still"] is True
    assert clip["motion"] == "kenburns"
