from __future__ import annotations

from pathlib import Path

from lc_editor.app import Editor
from lc_editor.models import Clip, ClipBlur, MediaItem, Project
from lc_editor.render.blurs import soft_mask_blur_chain
from lc_editor.render.graph import clip_hash_payload, clip_video_filters
from lc_editor.render.runner import FakeRunner


def _still_clip(editor: Editor, media_file: Path) -> str:
    still = media_file.with_suffix(".jpg")
    if not still.exists():
        still.write_bytes(b"\xff\xd8\xff\xd9")
    editor.import_file(str(still))
    editor.clip_add(media_id=editor.media[-1].id, duration_s=2.5)
    return editor.timeline_get()["timeline"]["clips"][-1]["id"]


def test_clip_blur_add_update_remove(editor: Editor, media_file: Path) -> None:
    clip_id = _still_clip(editor, media_file)
    added = editor.clip_blur_add(clip_id, kind="region", x=0.1, y=0.2, w=0.3, h=0.25)
    assert added["ok"] is True
    blur_id = added["blur_id"]
    assert blur_id
    listed = editor.clip_blur_list(clip_id)
    assert listed["ok"] is True
    assert len(listed["blurs"]) == 1
    assert listed["blurs"][0]["kind"] == "region"
    assert listed["blurs"][0]["x"] == 0.1
    moved = editor.clip_blur_update(blur_id, x=0.15, strength=18.0, feather=10.0)
    assert moved["ok"] is True
    row = editor.clip_blur_list(clip_id)["blurs"][0]
    assert row["x"] == 0.15
    assert row["strength"] == 18.0
    assert row["feather"] == 10.0
    removed = editor.clip_blur_remove(blur_id)
    assert removed["ok"] is True
    assert editor.clip_blur_list(clip_id)["blurs"] == []


def test_clip_blur_region_requires_box(editor: Editor, media_file: Path) -> None:
    clip_id = _still_clip(editor, media_file)
    bad = editor.clip_blur_add(clip_id, kind="region")
    assert bad["ok"] is False
    assert any("region" in w for w in bad["warnings"])


def test_clip_blur_face_missing_is_ok_warning(editor: Editor, media_file: Path) -> None:
    clip_id = _still_clip(editor, media_file)
    out = editor.clip_blur_add(clip_id, kind="face")
    assert out["ok"] is True
    assert out.get("blur_id") is None
    assert any("no face" in w.lower() or "no blur" in w.lower() for w in out["warnings"])
    assert editor.clip_blur_list(clip_id)["blurs"] == []


def test_export_graph_includes_soft_mask_blur(editor: Editor, media_file: Path) -> None:
    editor.import_file(str(media_file))
    editor.clip_add(media_id=editor.media[-1].id, duration_s=5.0)
    clip_id = editor.timeline_get()["timeline"]["clips"][-1]["id"]
    added = editor.clip_blur_add(clip_id, kind="face", x=0.35, y=0.2, w=0.3, h=0.22)
    assert added["ok"] is True
    assert editor.review_report(allow_dense=True)["ok"] is True
    result = editor.export(preset="reel", wait=True)
    assert result["ok"] is True
    clip_blob = " ".join(
        " ".join(c) for c in editor.runner.calls if c and "/clips/" in c[-1].replace("\\", "/")
    )
    assert "gblur" in clip_blob
    assert "maskedmerge" in clip_blob


def test_soft_mask_filter_after_fit_in_clip_graph() -> None:
    blur = ClipBlur(id="blur_ab12", kind="region", x=0.1, y=0.2, w=0.25, h=0.2, strength=15.0, feather=12.0)
    clip = Clip(id="c1", media_id="m1", fit="cover", blurs=[blur])
    media = MediaItem(id="m1", path="x.jpg", original_path="x.jpg", kind="image", width=1080, height=1920)
    project = Project(id="p", name="n")
    filt = clip_video_filters(clip, media, [], project)
    assert "maskedmerge" in filt
    assert "gblur" in filt
    # Fit (cover increase) appears before the soft-mask split.
    assert filt.index("force_original_aspect_ratio=increase") < filt.index("split=3")
    payload = clip_hash_payload(clip, [], project)
    assert payload["blurs"][0]["id"] == "blur_ab12"
    chain = soft_mask_blur_chain([blur], 1080, 1920)
    assert "maskedmerge" in chain
    assert "15.00" in chain or "26.67" in chain  # scaled by 1920/1080


def test_mcp_blur_tools_named_fields(tmp_path: Path) -> None:
    from lc_editor.server import TOOLS, build_mcp

    editor = Editor(workspace=tmp_path, runner=FakeRunner())
    mcp = build_mcp(editor)
    manager = getattr(mcp, "_tool_manager", None)
    tools = {}
    if manager is not None and hasattr(manager, "_tools"):
        for name, tool in manager._tools.items():
            fn = getattr(tool, "fn", None) or getattr(tool, "handler", None)
            import inspect

            props = {k: {} for k in inspect.signature(fn).parameters}
            tools[name] = {"properties": props}
    assert "clip_blur_add" in TOOLS
    add = tools["clip_blur_add"]["properties"]
    assert "clip_id" in add
    assert "kind" in add
    assert "x" in add and "y" in add and "w" in add and "h" in add
    assert "kwargs" not in add
    assert "blur_id" in tools["clip_blur_update"]["properties"]
    assert "clip_id" in tools["clip_blur_list"]["properties"]
