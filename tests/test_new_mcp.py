"""Exercise the real stdio transport without relying on provider availability."""
import asyncio
import os
from pathlib import Path
import sys
import unittest

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


class NewServerTransportTests(unittest.IsolatedAsyncioTestCase):
    async def test_initialize_discover_and_call_all_seven_servers(self):
        tools = {
            "gdc": (6, "gdc_projects", {"limit": 0}),
            "reactome": (5, "reactome_search", {"query": ""}),
            "cellxgene": (6, "cellxgene_versions", {"limit": 0}),
            "chembl": (6, "chembl_search", {"query": ""}),
            "gwas": (5, "gwas_traits", {"query": ""}),
            "opentargets": (6, "opentargets_search", {"query": ""}),
            "cbioportal": (6, "cbioportal_studies", {"limit": 0}),
        }
        for provider, (count, tool, arguments) in tools.items():
            with self.subTest(provider=provider):
                params = StdioServerParameters(command=sys.executable,
                    args=["-m", f"servers.{provider}_mcp.server"],
                    cwd=str(Path(__file__).resolve().parents[1]), env=dict(os.environ))
                async def check_connection():
                    async with stdio_client(params) as (read, write):
                        async with ClientSession(read, write) as session:
                            await session.initialize()
                            discovered = (await session.list_tools()).tools
                            self.assertEqual(len(discovered), count)
                            self.assertIn(tool, [item.name for item in discovered])
                            result = await session.call_tool(tool, arguments)
                            self.assertTrue(result.isError)
                await asyncio.wait_for(check_connection(), timeout=20)
