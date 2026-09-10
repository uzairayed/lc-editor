from __future__ import annotations

from pathlib import Path

import pytest

from lc_editor import __version__
from lc_editor.cli import build_parser, main
from lc_editor.doctor import SMOKE_TOOLS, doctor_payload, format_doctor, package_version, project_status
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
    assert "ffmpeg: /bin/ffmpeg" in out
    assert "ffprobe: /bin/ffprobe" in out
    assert f"mcp_tools: {len(TOOLS)}" in out
    for name in SMOKE_TOOLS:
        assert f"{name}: ok" in out
    assert "ok: true" in out


def test_doctor_red_when_ffmpeg_missing(monkeypatch, capsys) -> None:
    monkeypatch.setattr("lc_editor.doctor.which_tool", lambda name: None)
    assert main(["doctor"]) == 1
    out = capsys.readouterr().out
    assert "ffmpeg: missing" in out
    assert "ffprobe: missing" in out
    assert "ok: false" in out


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
    project = payload["project"]
    assert isinstance(project, dict)
    assert project["exists"] is True
    assert "exists" in str(project["note"])
    assert "project:" in format_doctor(payload)


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
