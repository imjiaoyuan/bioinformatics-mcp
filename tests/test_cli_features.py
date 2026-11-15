"""Tests for CLI features: uvx ref pinning, config naming, register --remove, doctor, and serve aggregation."""
from __future__ import annotations

import asyncio
import json
import tempfile
import unittest
from pathlib import Path
from types import ModuleType
from unittest.mock import AsyncMock, patch

from mcp.server.mcpserver import MCPServer

from common import cli, doctor, serve


def _tool(name: str):
    async def tool() -> dict:
        """Stub tool for registration tests."""
        return {}
    tool.__name__ = name
    return tool


def _api_module(name: str, *tools) -> ModuleType:
    module = ModuleType(f"servers.{name}_mcp.api")
    module.TOOLS = tuple(_tool(tool) for tool in tools)
    module.RESOURCES = ()
    return module


class BuildEntriesTests(unittest.TestCase):
    def test_uvx_entries_pin_the_requested_ref(self):
        entries = cli.build_entries(["ensembl"], serve=False, uvx=True, ref="v0.2.0")
        self.assertEqual(entries["ensembl"]["args"],
                         ["--from", cli.SOURCE + "@v0.2.0", "ensembl-mcp"])

    def test_serve_entry_uses_the_requested_name(self):
        entries = cli.build_entries(["ensembl"], serve=True, uvx=False, name="bio-core")
        self.assertEqual(list(entries), ["bio-core"])


class MergeConfigTests(unittest.TestCase):
    def test_remove_deletes_only_the_selected_entries(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "config.json"
            path.write_text(json.dumps({"mcpServers": {
                "ensembl": {"command": "/x/ensembl-mcp"},
                "pdb": {"command": "/x/pdb-mcp"},
            }}))
            cli.merge_config(path, {"ensembl": {"command": "/x/ensembl-mcp"}}, replace=False, remove=True)
            config = json.loads(path.read_text())
            self.assertNotIn("ensembl", config["mcpServers"])
            self.assertIn("pdb", config["mcpServers"])

    def test_remove_rejects_unknown_entries(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "config.json"
            path.write_text(json.dumps({"mcpServers": {}}))
            with self.assertRaises(ValueError):
                cli.merge_config(path, {"ensembl": {}}, replace=False, remove=True)


class ServeAggregationTests(unittest.IsolatedAsyncioTestCase):
    async def test_duplicate_tool_names_get_namespaced(self):
        alpha = _api_module("alpha", "lookup")
        beta = _api_module("beta", "lookup", "beta_only")
        mcp = MCPServer("aggregate")
        registered: dict[str, str] = {}
        serve.register(mcp, alpha, "alpha", registered)
        serve.register(mcp, beta, "beta", registered)
        tools = await mcp.list_tools()
        names = sorted(tool.name for tool in tools)
        self.assertEqual(names, ["beta_lookup", "beta_only", "lookup"])
        self.assertEqual(registered["lookup"], "alpha")
        clash = next(tool for tool in tools if tool.name == "beta_lookup")
        self.assertIn("[beta]", clash.description)

    async def test_registered_tools_carry_read_only_annotations(self):
        mcp = MCPServer("alpha")
        api = _api_module("alpha", "lookup", "submit_job")
        api.MUTATING = ("submit_job",)
        serve.register(mcp, api, "alpha")
        tools = {tool.name: tool for tool in await mcp.list_tools()}
        self.assertTrue(tools["lookup"].annotations.read_only_hint)
        self.assertIsNone(tools["submit_job"].annotations)

    async def test_meta_status_resource_is_registered(self):
        mcp = MCPServer("alpha")
        serve.register_status(mcp, "alpha")
        resources = await mcp.list_resources()
        self.assertEqual(str(resources[0].uri), "meta://status")


class DoctorTests(unittest.IsolatedAsyncioTestCase):
    def test_report_flags_missing_environment_without_starting_servers(self):
        with patch.object(doctor, "server_commands", return_value={"ncbi": "ncbi-mcp"}), \
                patch.object(doctor, "probe", new_callable=AsyncMock) as probe, \
                patch.dict("os.environ", {}, clear=True), \
                patch.object(doctor, "latest_version", new_callable=AsyncMock, return_value="9.9.9"), \
                patch.object(doctor, "installed_version", return_value="0.1.0"):
            code = doctor.report(["ncbi"], check_release=True)
        self.assertEqual(code, 1)
        probe.assert_not_called()

    def test_report_starts_and_reports_healthy_providers(self):
        with patch.object(doctor, "server_commands", return_value={"ensembl": "ensembl-mcp"}), \
                patch.object(doctor, "probe", new_callable=AsyncMock, return_value=["ensembl_lookup"]), \
                patch.object(doctor, "find_command", return_value="/usr/bin/ensembl-mcp"), \
                patch.dict("os.environ", {}, clear=True), \
                patch.object(doctor, "latest_version", new_callable=AsyncMock, return_value="0.1.0"), \
                patch.object(doctor, "installed_version", return_value="0.1.0"):
            code = doctor.report(["ensembl"], check_release=True)
        self.assertEqual(code, 0)

    def test_upgrade_command_prefers_uv_tool_when_installed(self):
        real_which = __import__("shutil").which
        with patch("shutil.which", side_effect=lambda name: "/usr/bin/uv" if name == "uv" else real_which(name)), \
                patch("subprocess.run") as run:
            run.returncode = 0
            __import__("subprocess").run.return_value = type("R", (), {"returncode": 0, "stdout": "bioinformatics-mcp"})()
            command = doctor.upgrade_command()
        self.assertEqual(command[:3], ["/usr/bin/uv", "tool", "upgrade"])


if __name__ == "__main__":
    unittest.main()
