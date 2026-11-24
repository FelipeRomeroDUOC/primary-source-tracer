import json
import os
import shutil
import subprocess
import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent


class TestPortablePackage(unittest.TestCase):
    def test_1_no_hardcoded_user_paths_in_portable_configs(self):
        for rel in (
            "mcp_config.json",
            ".mcp.json",
            "pyproject.toml",
            "plugin.json",
            "README.md",
            ".claude-plugin/plugin.json",
            ".claude-plugin/marketplace.json",
            "gemini-extension.json",
        ):
            content = (REPO_ROOT / rel).read_text(encoding="utf-8")
            self.assertNotIn("C:/Users/", content, f"Hardcoded path found in {rel}")
            self.assertNotIn("C:\\Users\\", content, f"Hardcoded path found in {rel}")

    def test_2_module_entrypoint_stdio_roundtrip(self):
        env = os.environ.copy()
        env["PYTHONPATH"] = str(REPO_ROOT)
        proc = subprocess.Popen(
            [sys.executable, "-m", "primary_source_tracer.server"],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            env=env,
        )
        out, err = proc.communicate(
            input=json.dumps({"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}}) + "\n",
            timeout=5,
        )
        resp = json.loads(out.strip().splitlines()[0])
        self.assertEqual(len(resp["result"]["tools"]), 4)

    def test_3_console_script_entrypoint_if_installed(self):
        exe = shutil.which("primary-source-tracer-mcp")
        if not exe:
            scripts_dir = Path(sys.executable).parent / "Scripts"
            candidate = scripts_dir / "primary-source-tracer-mcp.exe"
            if candidate.exists():
                exe = str(candidate)
        self.assertIsNotNone(exe, "primary-source-tracer-mcp entrypoint not found; run pip install -e .")
        proc = subprocess.Popen(
            [exe],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
        )
        out, err = proc.communicate(
            input=json.dumps({"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}}) + "\n",
            timeout=5,
        )
        resp = json.loads(out.strip().splitlines()[0])
        self.assertEqual(len(resp["result"]["tools"]), 4)


if __name__ == "__main__":
    unittest.main()
