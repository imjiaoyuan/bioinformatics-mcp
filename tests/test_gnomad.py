"""Mocked tests for the gnomAD MCP api."""
import httpx

from servers.gnomad_mcp import api
from tests.helpers import HTTPTestCase

VARIANT = {"data": {"variant": {"variantId": "1-55039763-C-A", "rsid": None, "chrom": "1",
                                "pos": 55039763, "ref": "C", "alt": "A",
                                "reference_genome": "GRCh38",
                                "genome": {"ac": 2, "an": 76432, "af": 0.0000262, "ac_hom": 0},
                                "exome": {"ac": 0, "an": 1374942, "af": 0, "ac_hom": 0}}}}
GENE = {"data": {"gene": {"gene_id": "ENSG00000169174", "symbol": "PCSK9", "hgnc_id": "HGNC:20001",
                          "name": "proprotein convertase subtilisin/kexin type 9", "chrom": "1",
                          "start": 55039447, "stop": 55064852,
                          "mane_select_transcript": {"ensembl_id": "ENST00000302118",
                                                     "refseq_id": "NM_174936"},
                          "gnomad_constraint": {"oe_mis_upper": 0.95, "oe_lof_upper": 1.14,
                                                "mis_z": 1.23, "lof_z": 1.8, "pLI": 0.03}}}}
SEARCH = {"data": {"gene_search": [{"ensembl_id": "ENSG00000139618", "ensembl_version": "17",
                                    "symbol": "BRCA2"},
                                   {"ensembl_id": "ENSG00000012048", "ensembl_version": "23",
                                    "symbol": "BRCA1"}]}}


def response_for(query: str):
    if "variant(variantId" in query:
        return httpx.Response(200, json=VARIANT)
    if "gene(gene_symbol" in query:
        return httpx.Response(200, json=GENE)
    if "gene_search(" in query:
        return httpx.Response(200, json=SEARCH)
    raise AssertionError(f"unexpected query: {query}")


class GnomadTests(HTTPTestCase):
    async def test_variant_gene_and_search(self):
        seen = []

        def handler(req):
            seen.append(req.read().decode())
            return response_for(req.read().decode())

        with self.mock_http(handler):
            variant = await api.gnomad_variant("1-55039763-C-A", dataset="gnomad_r4")
            self.assertEqual(variant["data"]["variant"]["variantId"], "1-55039763-C-A")
            self.assertEqual(variant["data"]["variant"]["genome"]["an"], 76432)
            gene = await api.gnomad_gene("pcsk9")
            self.assertEqual(gene["data"]["gene"]["symbol"], "PCSK9")
            self.assertEqual(gene["data"]["gene"]["mane_select_transcript"]["refseq_id"], "NM_174936")
            self.assertEqual(gene["data"]["gene"]["gnomad_constraint"]["pLI"], 0.03)
            search = await api.gnomad_gene_search("BRCA", limit=1)
            self.assertEqual(search["results"][0]["symbol"], "BRCA2")
            self.assertEqual(search["total"], 2)
            self.assertTrue(search["truncated"])
        self.assertEqual(len(seen), 3)

    async def test_graphql_error_becomes_value_error(self):
        def handler(req):
            return httpx.Response(200, json={"errors": [{"message": "Variant not found"}]})

        with self.mock_http(handler):
            with self.assertRaisesRegex(ValueError, "Variant not found"):
                await api.gnomad_variant("1-55039763-C-A")

    async def test_validation_before_network(self):
        cases = [(api.gnomad_variant, {"variant_id": "1-55039763"}),
                 (api.gnomad_variant, {"variant_id": "chr1-55039763-C-A"}),
                 (api.gnomad_variant, {"variant_id": "1-55039763-C-A", "dataset": "gnomad_r5"}),
                 (api.gnomad_variant, {"variant_id": "1--C-A"}),
                 (api.gnomad_gene, {"gene_symbol": "PCSK9 x"}),
                 (api.gnomad_gene, {"gene_symbol": "PCSK9", "reference_genome": "GRCh39"}),
                 (api.gnomad_gene_search, {"query": ""}),
                 (api.gnomad_gene_search, {"query": "BRCA", "limit": 0})]
        for func, kwargs in cases:
            with self.subTest(tool=func.__name__, kwargs=kwargs), self.assertRaises(ValueError):
                await func(**kwargs)

    async def test_api_error(self):
        with self.mock_http(lambda req: httpx.Response(503)):
            with self.assertRaises(httpx.HTTPStatusError):
                await api.gnomad_gene("PCSK9")
