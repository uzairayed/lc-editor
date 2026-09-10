from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

from lc_editor.server import TOOLS

SMOKE_TOOLS = ("project_create", "import_file", "import_folder", "clip_add", "export")


def package_version() -> str:
    try:
        from importlib.metadata import version

        return version("lc-editor")
    except Exception:
        from lc_editor import __version__

        return __version__


def which_tool(name: str) -> str | None:
    return shutil.which(name)


def entrypoints() -> dict[str, bool]:
    found = {name: name in TOOLS for name in SMOKE_TOOLS}
    try:
        from lc_editor.app import Editor
    except Exception:
        return found
    for name in SMOKE_TOOLS:
        found[name] = found[name] and callable(getattr(Editor, name, None))
    return found


def project_status(project: Path) -> dict[str, object]:
    try:
        root = project.expanduser().resolve(strict=False)
    except OSError:
        root = project.expanduser().absolute()
    marker = root / "project.json"
    exists = marker.is_file()
    if exists:
        return {"path": str(root), "exists": True, "can_create": True, "note": "exists"}
    if root.is_file():
        return {"path": str(root), "exists": False, "can_create": False, "note": "blocked: path is a file"}
    parent = root.parent
    can_create = parent.is_dir() or parent.parent.is_dir()
    note = "missing, can create" if can_create else "missing, cannot create"
    return {"path": str(root), "exists": False, "can_create": can_create, "note": note}


def attach_command(bin_path: object) -> str:
    if isinstance(bin_path, str) and bin_path:
        return bin_path
    return "lc-editor"


def grok_mcp_json(command: str) -> dict[str, object]:
    return {"command": command, "args": ["serve"], "env": {}}


def cursor_mcp_json(command: str) -> dict[str, object]:
    return {"mcpServers": {"lc-editor": grok_mcp_json(command)}}


def smoke_ok(payload: dict[str, object]) -> bool:
    tools = payload.get("entrypoints") or {}
    return isinstance(tools, dict) and all(tools.get(name) for name in SMOKE_TOOLS)


def tools_invisible(payload: dict[str, object]) -> bool:
    return not payload.get("lc_editor_bin") or not smoke_ok(payload)


def doctor_payload(project: Path | None = None) -> dict[str, object]:
    py = sys.version_info
    bins = {name: which_tool(name) for name in ("ffmpeg", "ffprobe", "lc-editor")}
    tools = entrypoints()
    payload: dict[str, object] = {
        "version": package_version(),
        "python": f"{py.major}.{py.minor}.{py.micro}",
        "python_ok": py >= (3, 11),
        "lc_editor_bin": bins["lc-editor"],
        "ffmpeg": bins["ffmpeg"],
        "ffprobe": bins["ffprobe"],
        "mcp_tools": len(TOOLS),
        "entrypoints": tools,
        "project": project_status(project) if project is not None else None,
    }
    payload["ok"] = doctor_ok(payload)
    return payload


def doctor_ok(payload: dict[str, object]) -> bool:
    if not payload.get("python_ok"):
        return False
    if not payload.get("ffmpeg") or not payload.get("ffprobe"):
        return False
    if int(payload.get("mcp_tools") or 0) < 1:
        return False
    if not smoke_ok(payload):
        return False
    project = payload.get("project")
    if isinstance(project, dict) and not project.get("exists") and not project.get("can_create"):
        return False
    return True


def format_doctor(payload: dict[str, object]) -> str:
    command = attach_command(payload.get("lc_editor_bin"))
    lines = [
        f"lc-editor {payload['version']}",
        f"python: {payload['python']}",
        f"lc_editor_bin: {payload.get('lc_editor_bin') or 'missing'}",
        f"ffmpeg: {payload['ffmpeg'] or 'missing'}",
        f"ffprobe: {payload['ffprobe'] or 'missing'}",
        f"mcp_tools: {payload['mcp_tools']}",
    ]
    tools = payload.get("entrypoints") or {}
    if isinstance(tools, dict):
        for name in SMOKE_TOOLS:
            lines.append(f"{name}: {'ok' if tools.get(name) else 'missing'}")
    project = payload.get("project")
    if isinstance(project, dict):
        lines.append(f"project: {project['path']} {project['note']}")
    lines.append(f"ok: {str(payload['ok']).lower()}")
    if tools_invisible(payload):
        lines.append(
            "attach: tools will be invisible to the agent until AddMcpServer / PATH fix (#29/#32)"
        )
    else:
        lines.append("attach: #29/#32 - paste MCP JSON below; after pip install -U lc-editor, restart MCP")
    lines.append(
        "restart: Cursor RestartMcpServers; Grok Bot re-attach. Then confirm project_create is callable."
    )
    lines.append("Grok Bot AddMcpServer:")
    lines.append(json.dumps(grok_mcp_json(command), indent=2))
    lines.append("Cursor mcp.json:")
    lines.append(json.dumps(cursor_mcp_json(command), indent=2))
    return "\n".join(lines) + "\n"
