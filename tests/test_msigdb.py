import httpx

from servers.msigdb_mcp import api
from tests.helpers import HTTPTestCase

from unittest.mock import AsyncMock, patch

ENTRY = {"systematicName": "M5905", "pmid": "26771021", "exactSource": "",
         "geneSymbols": ["ABCA1", "ADIPOQ", "LEP"], "collection": "H",
         "msigdbURL": "https://www.gsea-msigdb.org/gsea/msigdb/human/geneset/HALLMARK_ADIPOGENESIS",
         "externalDetailsURL": [], "filteredBySimilarity": [],
         "externalNamesForSimilarTerms": []}


class MSigDBTests(HTTPTestCase):
    async def test_gene_set_and_genes(self):
        paths = []

        def handler(req):
            paths.append(req.url.path)
            return httpx.Response(200, json={"HALLMARK_ADIPOGENESIS": ENTRY})

        with self.mock_http(handler), patch("common.http.asyncio.sleep", new_callable=AsyncMock):
            detail = await api.msigdb_gene_set("human", "hallmark_adipogenesis")
            self.assertEqual(detail["systematic_name"], "M5905")
            self.assertEqual(detail["collection"], "H")
            self.assertEqual(detail["pmid"], "26771021")
            self.assertEqual(detail["genes"], ["ABCA1", "ADIPOQ", "LEP"])
            self.assertIn("source_url", detail)
            genes = await api.msigdb_gene_set_genes("human", "HALLMARK_ADIPOGENESIS",
                                                       limit=2, offset=1)
            self.assertEqual(genes["results"], ["ADIPOQ", "LEP"])
            self.assertEqual(genes["total"], 3)
            self.assertFalse(genes["truncated"])
            self.assertEqual(genes["pagination"], "local")
        self.assertIn("/gsea/msigdb/human/geneset/HALLMARK_ADIPOGENESIS.json", paths)

    async def test_batch_gene_sets_and_collections(self):
        def handler(req):
            if "APPLE" in req.url.path:
                return httpx.Response(200, content=b"<html>no such gene set</html>")
            return httpx.Response(200, json={"HALLMARK_ADIPOGENESIS": ENTRY})

        with self.mock_http(handler), patch("common.http.asyncio.sleep", new_callable=AsyncMock):
            batch = await api.msigdb_gene_sets("human", ["HALLMARK_ADIPOGENESIS", "APPLE"])
            self.assertEqual(batch["results"][0]["found"], True)
            self.assertEqual(batch["results"][1]["found"], False)
            catalog = await api.msigdb_collections("mouse")
            self.assertEqual([c["name"] for c in catalog["collections"]], ["M1", "M2", "M3", "M4", "M5"])
            self.assertIn("collections.jsp", catalog["source_url"])

    async def test_validation_all_tools(self):
        cases = [(api.msigdb_gene_set, {"species": "rat", "gene_set": "HALLMARK_ADIPOGENESIS"}),
                 (api.msigdb_gene_set, {"species": "human", "gene_set": "../etc"}),
                 (api.msigdb_gene_set_genes, {"species": "human", "gene_set": "HALLMARK_ADIPOGENESIS", "limit": 0}),
                 (api.msigdb_gene_set_genes, {"species": "human", "gene_set": "HALLMARK_ADIPOGENESIS", "limit": 101}),
                 (api.msigdb_gene_sets, {"species": "human", "gene_sets": []}),
                 (api.msigdb_gene_sets, {"species": "human", "gene_sets": ["A", "bad name"]}),
                 (api.msigdb_collections, {"species": "yeast"})]
        for func, args in cases:
            with self.subTest(tool=func.__name__), self.assertRaises(ValueError):
                await func(**args)

    async def test_unknown_gene_set(self):
        def handler(req):
            return httpx.Response(200, content=b"<html>no such gene set</html>")

        with self.mock_http(handler), patch("common.http.asyncio.sleep", new_callable=AsyncMock):
            with self.assertRaises(ValueError):
                await api.msigdb_gene_set("human", "NO_SUCH_SET")

    async def test_api_error(self):
        with self.mock_http(lambda req: httpx.Response(404)):
            with self.assertRaises(httpx.HTTPStatusError):
                await api.msigdb_gene_set("human", "HALLMARK_ADIPOGENESIS")
