from __future__ import annotations

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


def doctor_payload(project: Path | None = None) -> dict[str, object]:
    py = sys.version_info
    bins = {name: which_tool(name) for name in ("ffmpeg", "ffprobe")}
    tools = entrypoints()
    payload: dict[str, object] = {
        "version": package_version(),
        "python": f"{py.major}.{py.minor}.{py.micro}",
        "python_ok": py >= (3, 11),
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
    tools = payload.get("entrypoints") or {}
    if not isinstance(tools, dict) or not all(tools.get(name) for name in SMOKE_TOOLS):
        return False
    project = payload.get("project")
    if isinstance(project, dict) and not project.get("exists") and not project.get("can_create"):
        return False
    return True


def format_doctor(payload: dict[str, object]) -> str:
    lines = [
        f"lc-editor {payload['version']}",
        f"python: {payload['python']}",
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
    return "\n".join(lines) + "\n"
