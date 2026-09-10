from __future__ import annotations

import argparse
import threading
from pathlib import Path

from lc_editor.doctor import doctor_payload, format_doctor, package_version


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="lc-editor")
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("version", help="Print package version")
    doctor = sub.add_parser("doctor", help="Health check: ffmpeg, Python, MCP tools, attach JSON")
    doctor.add_argument("--project", default=None, help="Optional project path for a dry smoke")
    serve = sub.add_parser("serve", help="MCP stdio server")
    serve.add_argument("--project", default="./reel")
    serve.add_argument("--web", action="store_true")
    serve.add_argument("--web-port", type=int, default=8765)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.cmd == "version":
        return version_cmd()
    if args.cmd == "doctor":
        project = Path(args.project) if args.project else None
        return doctor_cmd(project)
    if args.cmd == "serve":
        return serve_cmd(Path(args.project), web=args.web, port=args.web_port)
    return 1


def version_cmd() -> int:
    print(package_version())
    return 0


def doctor_cmd(project: Path | None) -> int:
    payload = doctor_payload(project)
    print(format_doctor(payload), end="")
    return 0 if payload["ok"] else 1


def serve_cmd(project: Path, web: bool, port: int) -> int:
    from lc_editor.app import Editor
    from lc_editor.assets.pack import ensure_assets

    ensure_assets()
    editor = Editor(workspace=project.parent)
    if (project / "project.json").exists():
        editor.project_open(str(project))
    else:
        editor.project_create(name=project.name, project_dir=str(project))
    if web:
        from lc_editor.web.server import start_readonly_server

        thread = threading.Thread(
            target=start_readonly_server,
            args=(editor, "127.0.0.1", port),
            daemon=True,
        )
        thread.start()
    from lc_editor.server import run_stdio

    run_stdio(editor)
    return 0
