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


def test_spec_ses_11_python_311_ok() -> None:
    import sys

    assert sys.version_info >= (3, 11)
