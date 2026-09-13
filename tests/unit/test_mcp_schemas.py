from __future__ import annotations

from pathlib import Path

from lc_editor.app import Editor
from lc_editor.render.runner import FakeRunner
from lc_editor.server import TOOLS, build_mcp


def _schemas(tmp_path: Path) -> dict[str, dict]:
    editor = Editor(workspace=tmp_path, runner=FakeRunner())
    mcp = build_mcp(editor)
    manager = getattr(mcp, "_tool_manager", None)
    tools = []
    if manager is not None and hasattr(manager, "list_tools"):
        listed = manager.list_tools()
        tools = listed() if callable(listed) else listed
    elif hasattr(mcp, "list_tools"):
        tools = mcp.list_tools()
    out = {}
    for tool in tools:
        name = getattr(tool, "name", None)
        schema = getattr(tool, "parameters", None) or getattr(tool, "inputSchema", None)
        if callable(schema):
            schema = schema()
        if name:
            out[name] = schema or {}
    if not out and hasattr(manager, "_tools"):
        for name, tool in manager._tools.items():
            fn = getattr(tool, "fn", None) or getattr(tool, "handler", None)
            import inspect

            sig = inspect.signature(fn)
            props = {k: {} for k in sig.parameters}
            out[name] = {"properties": props, "type": "object"}
    return out


def test_spec_ses_10_mcp_tools_have_named_fields(tmp_path: Path) -> None:
    schemas = _schemas(tmp_path)
    assert set(TOOLS).issubset(schemas)
    clip_add = schemas["clip_add"]
    props = clip_add.get("properties") or clip_add.get("fields") or {}
    assert "media_id" in props
    assert "in_s" in props
    assert "kwargs" not in props
    caption = schemas["caption_add"]
    cprops = caption.get("properties") or {}
    assert "text" in cprops
    assert "clip_id" in cprops
    assert "op_id" in (schemas["clip_add"].get("properties") or {})
    tag = schemas["media_tag"].get("properties") or {}
    assert "media_id" in tag
    assert "shoot_day" in tag
    assert "role" in tag
    assert "kwargs" not in tag
    listed = schemas["media_list"].get("properties") or {}
    assert "shoot_day" in listed
    assert "role" in listed
    assert "min_motion" in listed
    analyze = schemas["media_analyze"].get("properties") or {}
    assert "media_id" in analyze
    assert "op_id" in analyze
    assert "kwargs" not in analyze
    search = schemas["shots_search"].get("properties") or {}
    assert "media_id" in search
    assert "shoot_day" in search
    assert "role" in search
    assert "min_motion" in search
    rank = schemas["shots_rank"].get("properties") or {}
    assert "role" in rank
    assert "top_k" in rank
    assert "shoot_day" in rank
    assert "kwargs" not in rank
    review = schemas["review_report"].get("properties") or {}
    assert "allow_dense" in review
    layout = schemas["layout_add"].get("properties") or {}
    assert "kind" in layout
    assert "panes" in layout
    assert "kwargs" not in layout
    zoom_pair = schemas["motion_zoom_pair"].get("properties") or {}
    assert "clip_id" in zoom_pair
    assert "frames_in" in zoom_pair
    assert "kwargs" not in zoom_pair
    suggest = schemas["motion_zoom_suggest"].get("properties") or {}
    assert "kwargs" not in suggest
    caption = schemas["caption_add"]
    cprops = caption.get("properties") or {}
    assert "style" in cprops
    assert "words" in cprops
    assert "font" in cprops
    text_style = schemas["text_style"].get("properties") or {}
    assert "font" in text_style
    project_set = schemas["project_set"].get("properties") or {}
    assert "caption_font" in project_set
    assert "duration_cap_s" in project_set
    assert "caption_contrast" in project_set
    contrast = project_set["caption_contrast"]
    contrast_blob = str(contrast).lower()
    assert "strict" in contrast_blob and "lenient" in contrast_blob
    preset = project_set.get("preset")
    preset_blob = str(preset).lower()
    assert "process" in preset_blob and "karachi" in preset_blob
    project_create = schemas["project_create"].get("properties") or {}
    create_preset = str(project_create.get("preset")).lower()
    assert "process" in create_preset and "karachi" in create_preset
    emphasis = schemas["caption_emphasis"].get("properties") or {}
    assert "word_id" in emphasis
    assert "kind" in emphasis
    cam = schemas["cam_pip"].get("properties") or {}
    assert "clip_id" in cam
    assert "x" in cam
    assert "w" in cam
    export = schemas["export"].get("properties") or {}
    assert "wait" in export
    assert "preset" in export
    preset_blob = str(export["preset"]).lower()
    assert "share" in preset_blob and "phone" in preset_blob and "reel" in preset_blob
    fit = schemas["clip_set_fit"].get("properties") or {}
    assert "clip_id" in fit
    assert "mode" in fit
    assert "kwargs" not in fit
    blur_add = schemas["clip_blur_add"].get("properties") or {}
    assert "clip_id" in blur_add
    assert "kind" in blur_add
    assert "x" in blur_add and "w" in blur_add
    kind_blob = str(blur_add.get("kind")).lower()
    assert "face" in kind_blob and "plate" in kind_blob and "region" in kind_blob
    assert "kwargs" not in blur_add
    blur_update = schemas["clip_blur_update"].get("properties") or {}
    assert "blur_id" in blur_update
    assert "strength" in blur_update
    assert "feather" in blur_update
    assert "kwargs" not in blur_update
    sfx_import = schemas["sfx_import"].get("properties") or {}
    assert "path" in sfx_import
    assert "kind" in sfx_import
    assert "source_name" in sfx_import
    assert "license" in sfx_import
    assert "source_url" in sfx_import
    assert "kwargs" not in sfx_import
    kind_blob = str(sfx_import.get("kind")).lower()
    for tag in ("whoosh", "swipe", "sparkle", "cash", "button", "correct"):
        assert tag in kind_blob
    license_blob = str(sfx_import.get("license")).lower()
    assert "cc0" in license_blob
    sfx_pack = schemas["sfx_pack_add"].get("properties") or {}
    assert "path" in sfx_pack
    assert "kind" in sfx_pack
    assert "source_name" in sfx_pack
    assert "license" in sfx_pack
    assert "kwargs" not in sfx_pack
    sfx_place = schemas["sfx_place"].get("properties") or {}
    assert "kind" in sfx_place
    assert "key" in sfx_place
    assert "at_s" in sfx_place
    assert "kwargs" not in sfx_place


def test_spec_ses_11_python_311_ok() -> None:
    import sys

    assert sys.version_info >= (3, 11)
