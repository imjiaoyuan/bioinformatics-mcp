"""Check all installed console scripts over real stdio, without provider requests.

This file is also copied into a clean directory by the distribution check. Keep
it independent of the source checkout, test helpers and optional provider SDKs.
"""
import asyncio
from importlib.metadata import distribution
import os
from pathlib import Path
import sys
import tempfile
import unittest

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


# Invalid arguments deliberately fail before a tool can access a provider.
# Missing required arguments also exercise older servers without bounded inputs.
SERVERS = {
    "anaconda": (3, "anaconda_search", {}),
    "bioconductor": (3, "bioconductor_package", {}),
    "biostudies": (4, "biostudies_search", {}),
    "cbioportal": (6, "cbioportal_studies", {"limit": 0}),
    "cellxgene": (6, "cellxgene_versions", {"limit": 0}),
    "chembl": (6, "chembl_search", {}),
    "cncb": (8, "cncb_genome", {}),
    "ena": (4, "ena_search", {}),
    "ensembl": (7, "ensembl_lookup", {}),
    "gdc": (6, "gdc_projects", {"limit": 0}),
    "gprofiler": (3, "gprofiler_enrichment", {}),
    "gwas": (5, "gwas_traits", {}),
    "interpro": (4, "interpro_search", {}),
    "ncbi": (14, "ncbi_search", {}),
    "opentargets": (6, "opentargets_search", {}),
    "pdb": (3, "pdb_entry", {}),
    "publications": (4, "publication_search", {}),
    "reactome": (5, "reactome_search", {}),
    "string": (3, "string_resolve", {}),
    "uniprot": (6, "uniprot_search", {}),
    "sra": (3, "sra_search", {}),
    "gtex": (6, "gtex_gene_search", {}),
    "hpa": (6, "hpa_search", {}),
    "alphafold": (4, "alphafold_prediction", {}),
    "emdb": (4, "emdb_entry", {}),
    "kegg": (5, "kegg_list", {}),
    "panglao": (5, "panglao_gene_markers", {}),
    "intact": (4, "intact_interaction_search", {}),
    "biogrid": (6, "biogrid_interactions", {}),
    "depmap": (8, "depmap_cell_line_sensitivity", {}),
    "civic": (6, "civic_search", {}),
    "clinvar": (4, "clinvar_search", {}),
    "pharmgkb": (6, "pharmgkb_drug", {}),
    "disgenet": (6, "disgenet_gene_diseases", {}),
    "mondo": (5, "mondo_search", {}),
    "hpo": (7, "hpo_search", {}),
    "quickgo": (4, "quickgo_go_term", {}),
    "singlecell": (7, "scp_search_studies", {}),
    "vep": (6, "vep_hgvs", {}),
    "ucsc": (5, "ucsc_get_data", {}),
    "mygene": (6, "mygene_query", {}),
    "bigg": (7, "bigg_search", {}),
    "bgee": (6, "bgee_gene_expression", {}),
    "pdbe": (7, "pdbe_entry_summary", {}),
    "msigdb": (4, "msigdb_gene_set", {}),
}


class ServerTransportTests(unittest.IsolatedAsyncioTestCase):
    def test_registered_entry_points(self):
        entries = {entry.name: entry.value for entry in
                   distribution("bioinformatics-mcp").entry_points
                   if entry.group == "console_scripts"}
        expected = {f"{provider}-mcp": f"servers.{provider}_mcp.server:main"
                    for provider in SERVERS}
        expected["bioinformatics-mcp"] = "common.cli:main"
        self.assertEqual(entries, expected)

    async def check_server(self, provider: str):
        count, tool, arguments = SERVERS[provider]
        suffix = ".exe" if os.name == "nt" else ""
        command = Path(sys.executable).parent / f"{provider}-mcp{suffix}"
        self.assertTrue(command.is_file(), f"Missing installed console script: {command}")
        env = {key: value for key, value in os.environ.items()
               if key not in {"PYTHONPATH", "PYTHONHOME"}}
        # Import from the installed package, not the repository's current directory.
        with tempfile.TemporaryDirectory(prefix=f"{provider}-mcp-stdio-") as directory:
            params = StdioServerParameters(command=str(command), cwd=directory, env=env)

            async def check_connection():
                async with stdio_client(params) as (read, write):
                    async with ClientSession(read, write) as session:
                        await session.initialize()
                        discovered = (await session.list_tools()).tools
                        names = [item.name for item in discovered]
                        self.assertEqual(len(names), count)
                        self.assertEqual(len(set(names)), count)
                        self.assertIn(tool, names)
                        result = await session.call_tool(tool, arguments)
                        self.assertTrue(result.isError)
                        self.assertTrue(result.content)
                        # Also check a successful, local-only tool response when available.
                        if provider == "pdb":
                            result = await session.call_tool("pdb_download_url", {"pdb_id": "4HHB"})
                            self.assertFalse(result.isError)
                            self.assertIn("4hhb.cif", str(result.content))
                        elif provider == "cncb":
                            result = await session.call_tool("cncb_database_catalog", {})
                            self.assertFalse(result.isError)
                            self.assertIn("ngdc.cncb.ac.cn/databases", str(result.content))

            await asyncio.wait_for(check_connection(), timeout=20)


def _transport_test(provider: str):
    async def test(self):
        await self.check_server(provider)
    test.__name__ = f"test_stdio_{provider}"
    return test


for _provider in SERVERS:
    setattr(ServerTransportTests, f"test_stdio_{_provider}", _transport_test(_provider))
