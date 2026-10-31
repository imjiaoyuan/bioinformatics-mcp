"""Offline checks for installed command discovery and configuration merging."""
from contextlib import redirect_stdout, redirect_stderr
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

from common import cli


class CliTests(unittest.TestCase):
    def invoke(self, *arguments):
        output = io.StringIO()
        with redirect_stdout(output):
            cli.main(list(arguments))
        return output.getvalue()

    def test_catalog_matches_provider_entry_points(self):
        from tests.test_mcp_transport import SERVERS
        self.assertEqual(set(cli.server_commands()), set(SERVERS))

    def test_json_uses_absolute_commands_without_checkout(self):
        with patch.object(cli.shutil, "which", return_value="/opt/tool bin/pdb-mcp"):
            config = json.loads(self.invoke("config", "pdb"))
        self.assertEqual(config, {"mcpServers": {"pdb": {"command": "/opt/tool bin/pdb-mcp"}}})

    def test_toml_forwards_variable_names_without_reading_secrets(self):
        with patch.object(cli, "find_command", return_value="/usr/bin/ncbi-mcp"):
            output = self.invoke("config", "ncbi", "--format", "toml")
        self.assertIn("[mcp_servers.ncbi]", output)
        self.assertIn('env_vars = ["NCBI_EMAIL", "NCBI_API_KEY", "NCBI_TOOL"]', output)
        self.assertNotIn("cwd", output)

    def test_fallback_to_interpreter_sibling(self):
        with tempfile.TemporaryDirectory() as directory:
            executable = Path(directory) / ("pdb-mcp.exe" if sys.platform == "win32" else "pdb-mcp")
            executable.touch(mode=0o755)
            with patch.object(cli.shutil, "which", return_value=None), \
                    patch.object(cli.sys, "executable", str(Path(directory) / "python")):
                self.assertEqual(cli.find_command("pdb-mcp"), str(executable))

    def test_missing_command_and_invalid_provider_fail(self):
        for arguments in (("config", "unknown"), ("config", "pdb")):
            with patch.object(cli, "find_command", side_effect=ValueError("Cannot find pdb-mcp")), \
                    redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as error:
                self.invoke(*arguments)
            self.assertEqual(error.exception.code, 2)

    def test_register_preserves_settings_and_backup_and_is_repeatable(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "mcp.json"
            original = '{"theme":"dark","mcpServers":{"other":{"command":"other"}}}'
            path.write_text(original)
            entries = {"pdb": {"command": "/usr/bin/pdb-mcp"}}
            cli.merge_config(path, entries, replace=False)
            result = json.loads(path.read_text())
            self.assertEqual(result["theme"], "dark")
            self.assertEqual(result["mcpServers"]["other"], {"command": "other"})
            self.assertEqual(result["mcpServers"]["pdb"], entries["pdb"])
            cli.merge_config(path, entries, replace=False)
            self.assertEqual(path.with_name("mcp.json.bak").read_text(), original)

    def test_conflicts_require_replace(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "mcp.json"
            original = '{"mcpServers":{"pdb":{"command":"old","env":{"X":"keep"}}}}'
            path.write_text(original)
            entries = {"pdb": {"command": "/usr/bin/pdb-mcp"}}
            with self.assertRaisesRegex(ValueError, "--replace"):
                cli.merge_config(path, entries, replace=False)
            self.assertEqual(path.read_text(), original)
            cli.merge_config(path, entries, replace=True)
            self.assertEqual(json.loads(path.read_text())["mcpServers"], entries)

    def test_invalid_config_is_untouched(self):
        for original in ("{", "[]", '{"mcpServers": []}'):
            with tempfile.TemporaryDirectory() as directory:
                path = Path(directory) / "mcp.json"
                path.write_text(original)
                with self.assertRaises(ValueError):
                    cli.merge_config(path, {}, replace=False)
                self.assertEqual(path.read_text(), original)

    def test_register_creates_missing_parent(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "nested" / "mcp.json"
            with patch.object(cli, "find_command", return_value="/usr/bin/pdb-mcp"):
                self.invoke("register", "pdb", "--config", str(path))
            self.assertEqual(json.loads(path.read_text())["mcpServers"]["pdb"]["command"],
                             "/usr/bin/pdb-mcp")
