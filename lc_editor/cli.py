from __future__ import annotations

import argparse
import threading
from pathlib import Path

from lc_editor.app import Editor
from lc_editor.assets.pack import ensure_assets


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="lc-editor")
    sub = parser.add_subparsers(dest="cmd", required=True)
    serve = sub.add_parser("serve", help="MCP stdio server")
    serve.add_argument("--project", default="./reel")
    serve.add_argument("--web", action="store_true")
    serve.add_argument("--web-port", type=int, default=8765)
    args = parser.parse_args(argv)

    if args.cmd == "serve":
        return serve_cmd(Path(args.project), web=args.web, port=args.web_port)
    return 1


def serve_cmd(project: Path, web: bool, port: int) -> int:
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
