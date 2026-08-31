from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def test_plugin_json_parses() -> None:
    plugin_path = ROOT / "plugin.json"
    assert plugin_path.exists(), "plugin.json missing"
    data = json.loads(plugin_path.read_text())
    assert data.get("$schema") == "https://agent-plugins.org/schemas/1.0.0/plugin.schema.json"
    assert data.get("name") == "lc-editor"
    assert "version" in data
    assert "description" in data


def test_mcp_json_parses() -> None:
    mcp_path = ROOT / "mcp.json"
    assert mcp_path.exists(), "mcp.json missing"
    data = json.loads(mcp_path.read_text())
    assert data.get("$schema") == "https://agent-plugins.org/schemas/1.0.0/mcp.schema.json"
    servers = data.get("mcpServers", {})
    assert "lc-editor" in servers
    server = servers["lc-editor"]
    assert server.get("type") == "stdio"
    assert "command" in server


def test_skill_md_exists() -> None:
    skill_path = ROOT / "skills" / "lc-editor" / "SKILL.md"
    assert skill_path.exists(), "skills/lc-editor/SKILL.md missing"
    content = skill_path.read_text()
    assert "lc-editor" in content
    assert "review_report" in content


def test_serve_help_works() -> None:
    result = subprocess.run(
        [sys.executable, "-m", "lc_editor", "serve", "--help"],
        capture_output=True,
        text=True,
        cwd=ROOT,
    )
    assert result.returncode == 0
    assert "--project" in result.stdout
    assert "--web" in result.stdout
