from __future__ import annotations

from pathlib import Path

import pytest

from lc_editor import __version__
from lc_editor.cli import build_parser, main
from lc_editor.doctor import (
    SMOKE_TOOLS,
    attach_command,
    cursor_mcp_json,
    doctor_payload,
    format_doctor,
    grok_mcp_json,
    package_version,
    project_status,
)
from lc_editor.server import TOOLS


def test_spec_ses_15_version_prints_package_version(capsys) -> None:
    assert main(["version"]) == 0
    printed = capsys.readouterr().out.strip()
    assert printed == package_version()
    assert printed
    assert __version__


def test_parser_accepts_version_and_doctor() -> None:
    parser = build_parser()
    version = parser.parse_args(["version"])
    assert version.cmd == "version"
    doctor = parser.parse_args(["doctor"])
    assert doctor.cmd == "doctor"
    assert doctor.project is None
    scoped = parser.parse_args(["doctor", "--project", "/abs/reel"])
    assert scoped.project == "/abs/reel"


def test_parser_keeps_serve_flags() -> None:
    args = build_parser().parse_args(["serve", "--project", "./reel", "--web", "--web-port", "9000"])
    assert args.cmd == "serve"
    assert args.project == "./reel"
    assert args.web is True
    assert args.web_port == 9000


def test_unknown_command_exits() -> None:
    with pytest.raises(SystemExit) as exc:
        main(["not-a-command"])
    assert exc.value.code != 0


def test_doctor_green_when_bins_present(monkeypatch, capsys) -> None:
    monkeypatch.setattr("lc_editor.doctor.which_tool", lambda name: f"/bin/{name}")
    assert main(["doctor"]) == 0
    out = capsys.readouterr().out
    assert f"lc-editor {package_version()}" in out
    assert "lc_editor_bin: /bin/lc-editor" in out
    assert "ffmpeg: /bin/ffmpeg" in out
    assert "ffprobe: /bin/ffprobe" in out
    assert f"mcp_tools: {len(TOOLS)}" in out
    for name in SMOKE_TOOLS:
        assert f"{name}: ok" in out
    assert "ok: true" in out
    assert "Grok Bot AddMcpServer:" in out
    assert '"command": "/bin/lc-editor"' in out
    assert '"serve"' in out
    assert '"env": {}' in out
    assert "Cursor mcp.json:" in out
    assert '"mcpServers"' in out
    assert "RestartMcpServers" in out
    assert "#29" in out
    assert "#32" in out
    assert "invisible" not in out


def test_doctor_red_when_ffmpeg_missing(monkeypatch, capsys) -> None:
    monkeypatch.setattr("lc_editor.doctor.which_tool", lambda name: None)
    assert main(["doctor"]) == 1
    out = capsys.readouterr().out
    assert "lc_editor_bin: missing" in out
    assert "ffmpeg: missing" in out
    assert "ffprobe: missing" in out
    assert "ok: false" in out
    assert "tools will be invisible" in out
    assert "AddMcpServer" in out
    assert '"command": "lc-editor"' in out
    assert "RestartMcpServers" in out


def test_doctor_ok_when_lc_editor_bin_missing(monkeypatch, capsys) -> None:
    def fake_which(name: str) -> str | None:
        if name == "lc-editor":
            return None
        return f"/bin/{name}"

    monkeypatch.setattr("lc_editor.doctor.which_tool", fake_which)
    payload = doctor_payload()
    assert payload["lc_editor_bin"] is None
    assert payload["ok"] is True
    assert main(["doctor"]) == 0
    out = capsys.readouterr().out
    assert "lc_editor_bin: missing" in out
    assert "ok: true" in out
    assert "tools will be invisible" in out
    assert "AddMcpServer" in out
    assert '"command": "lc-editor"' in out
    assert '"args": [' in out
    assert '"serve"' in out


def test_doctor_warns_when_entrypoints_missing(monkeypatch, capsys) -> None:
    monkeypatch.setattr("lc_editor.doctor.which_tool", lambda name: f"/bin/{name}")
    monkeypatch.setattr(
        "lc_editor.doctor.entrypoints",
        lambda: {name: False for name in SMOKE_TOOLS},
    )
    assert main(["doctor"]) == 1
    out = capsys.readouterr().out
    assert "project_create: missing" in out
    assert "ok: false" in out
    assert "tools will be invisible" in out
    assert '"command": "/bin/lc-editor"' in out


def test_doctor_attach_json_uses_resolved_bin() -> None:
    assert attach_command("/workspace/lc-editor-venv/bin/lc-editor") == (
        "/workspace/lc-editor-venv/bin/lc-editor"
    )
    assert attach_command(None) == "lc-editor"
    grok = grok_mcp_json("/bin/lc-editor")
    assert grok == {"command": "/bin/lc-editor", "args": ["serve"], "env": {}}
    cursor = cursor_mcp_json("/bin/lc-editor")
    assert cursor["mcpServers"]["lc-editor"] == grok


def test_doctor_project_is_dry_smoke(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr("lc_editor.doctor.which_tool", lambda name: f"/bin/{name}")
    missing = tmp_path / "new-reel"
    assert main(["doctor", "--project", str(missing)]) == 0
    assert not (missing / "project.json").exists()
    assert not missing.exists()

    existing = tmp_path / "reel"
    existing.mkdir()
    (existing / "project.json").write_text("{}")
    payload = doctor_payload(existing)
    assert payload["ok"] is True
    assert payload["lc_editor_bin"] == "/bin/lc-editor"
    project = payload["project"]
    assert isinstance(project, dict)
    assert project["exists"] is True
    assert "exists" in str(project["note"])
    rendered = format_doctor(payload)
    assert "project:" in rendered
    assert "Grok Bot AddMcpServer:" in rendered
    assert '"command": "/bin/lc-editor"' in rendered


def test_doctor_blocked_file_project(tmp_path: Path) -> None:
    blocker = tmp_path / "not-a-dir"
    blocker.write_text("nope")
    status = project_status(blocker)
    assert status["exists"] is False
    assert status["can_create"] is False


def test_doctor_does_not_export(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr("lc_editor.doctor.which_tool", lambda name: f"/bin/{name}")
    assert main(["doctor", "--project", str(tmp_path / "reel")]) == 0
    assert not (tmp_path / "reel" / "project.json").exists()
    assert not list(tmp_path.rglob("*.mp4"))
