import json
import subprocess
import sys
import unittest
from pathlib import Path

PLUGIN_DIR = Path(__file__).resolve().parent.parent
ALLOWED_PLUGIN_KEYS = {
    "name",
    "description",
    "logo",
    "suggestedPrompts",
    "displayName",
    "version",
    "author",
    "homepage",
    "repository",
    "disabled",
}


def test_plugin_json_and_mcp_config_valid():
    plugin_json = json.loads((PLUGIN_DIR / "plugin.json").read_text(encoding="utf-8"))
    assert plugin_json["name"] == "primary-source-tracer"
    assert set(plugin_json.keys()).issubset(ALLOWED_PLUGIN_KEYS)
    assert (PLUGIN_DIR / plugin_json["logo"]).exists()

    mcp_cfg = json.loads((PLUGIN_DIR / "mcp_config.json").read_text(encoding="utf-8"))
    assert "primary-source-tracer" in mcp_cfg["mcpServers"]

    dot_mcp = json.loads((PLUGIN_DIR / ".mcp.json").read_text(encoding="utf-8"))
    assert "primary-source-tracer" in dot_mcp["mcpServers"]

    claude_plugin = json.loads((PLUGIN_DIR / ".claude-plugin" / "plugin.json").read_text(encoding="utf-8"))
    assert claude_plugin["name"] == "primary-source-tracer"
    assert (PLUGIN_DIR / claude_plugin["skills"]).exists()

    claude_mkt = json.loads((PLUGIN_DIR / ".claude-plugin" / "marketplace.json").read_text(encoding="utf-8"))
    assert claude_mkt["plugins"][0]["name"] == "primary-source-tracer"

    gemini_ext = json.loads((PLUGIN_DIR / "gemini-extension.json").read_text(encoding="utf-8"))
    assert gemini_ext["name"] == "primary-source-tracer"
    assert (PLUGIN_DIR / gemini_ext["contextFileName"]).exists()
    assert "primary-source-tracer" in gemini_ext["mcpServers"]


def test_skill_and_rules_enforce_domain_agnostic_and_secondary_listing():
    skill_md = (PLUGIN_DIR / "skills" / "primary-source-search" / "SKILL.md").read_text(encoding="utf-8")
    assert "agent_evidence_markers" in skill_md
    assert "official_or_pdf_but_secondary" in skill_md
    assert "Fuentes Secundarias" in skill_md

    rules_md = (PLUGIN_DIR / "rules" / "AGENTS.md").read_text(encoding="utf-8")
    assert not rules_md.lstrip().startswith("---")


def test_mcp_server_stdio_subprocess_roundtrip():
    proc = subprocess.Popen(
        [sys.executable, str(PLUGIN_DIR / "primary_source_tracer" / "server.py")],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
    )
    out, err = proc.communicate(
        input=json.dumps({"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}}) + "\n",
        timeout=5,
    )
    resp = json.loads(out.strip().splitlines()[0])
    assert len(resp["result"]["tools"]) == 4


class TestPluginBundle(unittest.TestCase):
    def test_1_manifests(self):
        test_plugin_json_and_mcp_config_valid()

    def test_2_skill_and_rules(self):
        test_skill_and_rules_enforce_domain_agnostic_and_secondary_listing()

    def test_3_subprocess_stdio(self):
        test_mcp_server_stdio_roundtrip = test_mcp_server_stdio_subprocess_roundtrip
        test_mcp_server_stdio_roundtrip()


if __name__ == "__main__":
    unittest.main()
