from unittest.mock import AsyncMock, patch

import httpx

from servers.reactome_mcp import server
from tests.helpers import HTTPTestCase


class ReactomeTests(HTTPTestCase):
    async def test_search_uses_upstream_page_and_species(self):
        def handler(req):
            self.assertEqual(req.url.path, "/ContentService/search/query/paginated")
            self.assertEqual(req.url.params["page"], "2")
            self.assertEqual(req.url.params["rowCount"], "1")
            self.assertEqual(req.url.params["species"], "Homo sapiens")
            return httpx.Response(200, json={"results": [{"stId": "R-HSA-1"}], "rowCount": 4})
        with self.mock_http(handler):
            self.assertEqual((await server.reactome_search("p53", limit=1, page=2))["data"]["rowCount"], 4)

    async def test_entry_and_local_lists(self):
        paths = []
        def handler(req):
            paths.append(req.url.path)
            return httpx.Response(200, json={"stId": "R-HSA-1"} if "/query/" in req.url.path else [{"dbId": 1}, {"dbId": 2}])
        with self.mock_http(handler), patch("common.http.asyncio.sleep", new_callable=AsyncMock):
            self.assertEqual((await server.reactome_entry("R-HSA-1"))["data"]["stId"], "R-HSA-1")
            for result in [await server.reactome_pathway_events("R-HSA-1", limit=1),
                           await server.reactome_participants("R-HSA-1", limit=1),
                           await server.reactome_pathways_for_gene("P04637", limit=1)]:
                self.assertTrue(result["truncated"])
                self.assertEqual(result["pagination"], "local")
                self.assertEqual(result["total"], 2)
        self.assertIn("/ContentService/data/mapping/UniProt/P04637/pathways", paths)

    async def test_validation_all_tools(self):
        for func, args in [(server.reactome_search, {"query": ""}),
                           (server.reactome_entry, {"reactome_id": "bad"}),
                           (server.reactome_pathway_events, {"reactome_id": "R-HSA-1", "limit": 101}),
                           (server.reactome_participants, {"reactome_id": "../"}),
                           (server.reactome_pathways_for_gene, {"gene_id": "P04637", "resource": "unknown"})]:
            with self.subTest(tool=func.__name__), self.assertRaises(ValueError):
                await func(**args)

    async def test_error_and_empty(self):
        with self.mock_http(lambda req: httpx.Response(404)):
            with self.assertRaises(httpx.HTTPStatusError):
                await server.reactome_entry("R-HSA-1")
        with self.mock_http(lambda req: httpx.Response(200, json=[])):
            self.assertEqual((await server.reactome_participants("R-HSA-1"))["total"], 0)
