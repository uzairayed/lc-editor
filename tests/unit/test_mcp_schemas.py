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
    analyze = schemas["media_analyze"].get("properties") or {}
    assert "media_id" in analyze
    assert "op_id" in analyze
    assert "kwargs" not in analyze
    search = schemas["shots_search"].get("properties") or {}
    assert "media_id" in search
    rank = schemas["shots_rank"].get("properties") or {}
    assert "role" in rank
    assert "top_k" in rank
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
    emphasis = schemas["caption_emphasis"].get("properties") or {}
    assert "word_id" in emphasis
    assert "kind" in emphasis
    export = schemas["export"].get("properties") or {}
    assert "wait" in export


def test_spec_ses_11_python_311_ok() -> None:
    import sys

    assert sys.version_info >= (3, 11)
