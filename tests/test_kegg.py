from unittest.mock import AsyncMock, patch

import httpx

from servers.kegg_mcp import server
from tests.helpers import HTTPTestCase


class KEGGTests(HTTPTestCase):
    async def test_all_tools(self):
        paths = []

        def handler(req):
            paths.append(req.url.path)
            body = "path:hsa00010\tGlycolysis - Human\npath:hsa00020\tCitrate cycle\n"
            if req.url.path == "/list/pathway/hsa":
                return httpx.Response(200, text=body)
            if req.url.path == "/find/compound/C7H10O5/formula":
                return httpx.Response(200, text="cpd:C06293\tShikimate\n")
            if req.url.path == "/get/hsa:10458":
                return httpx.Response(200, text="ENTRY       10458            Gene\n")
            if req.url.path == "/get/hsa:10458/aaseq":
                return httpx.Response(200, text=">hsa:10458\nMEEPQSDPSV\n")
            if req.url.path == "/link/pathway/hsa:10458":
                return httpx.Response(200, text="hsa:10458\tpath:hsa04115\n")
            if req.url.path == "/conv/ncbi-geneid/hsa:10458":
                return httpx.Response(200, text="ncbi-geneid:10458\thsa:10458\n")
            return httpx.Response(400)

        with self.mock_http(handler), patch("common.http.asyncio.sleep", new_callable=AsyncMock):
            listing = await server.kegg_list("pathway", organism="hsa", limit=1, offset=0)
            self.assertEqual(listing["results"][0]["id"], "path:hsa00010")
            self.assertEqual(listing["total"], 2)
            self.assertTrue(listing["truncated"])
            self.assertEqual(listing["pagination"], "local")
            found = await server.kegg_find("compound", "C7H10O5", option="formula")
            self.assertEqual(found["results"][0]["id"], "cpd:C06293")
            record = await server.kegg_get(["hsa:10458"])
            self.assertIn("ENTRY", record["text"])
            self.assertEqual(record["entry_ids"], "hsa:10458")
            seq = await server.kegg_get(["hsa:10458"], option="aaseq")
            self.assertIn("MEEPQSDPSV", seq["text"])
            links = await server.kegg_link("pathway", ["hsa:10458"])
            self.assertEqual(links["results"][0]["description"], "path:hsa04115")
            conv = await server.kegg_conv("ncbi-geneid", ["hsa:10458"])
            self.assertEqual(conv["results"][0]["id"], "ncbi-geneid:10458")
        self.assertEqual(
            paths, ["/list/pathway/hsa", "/find/compound/C7H10O5/formula", "/get/hsa:10458",
                    "/get/hsa:10458/aaseq", "/link/pathway/hsa:10458",
                    "/conv/ncbi-geneid/hsa:10458"])

    async def test_validation_all_tools(self):
        for func, args in [(server.kegg_list, {"database": "bad"}),
                           (server.kegg_list, {"database": "pathway", "organism": "hs"}),
                           (server.kegg_list, {"database": "pathway", "limit": 0}),
                           (server.kegg_find, {"database": "ko", "query": ""}),
                           (server.kegg_find, {"database": "ko", "query": "x", "option": "formula"}),
                           (server.kegg_find, {"database": "compound", "query": "x", "option": "bad"}),
                           (server.kegg_get, {"entry_ids": []}),
                           (server.kegg_get, {"entry_ids": ["../etc"]}),
                           (server.kegg_get, {"entry_ids": ["hsa:10458"], "option": "bad"}),
                           (server.kegg_link, {"target_db": "bad", "entry_ids": ["hsa:10458"]}),
                           (server.kegg_link, {"target_db": "pathway", "entry_ids": ["x" * 200]}),
                           (server.kegg_conv, {"target_db": "ncbi-gene", "entry_ids": ["hsa:10458"]}),
                           (server.kegg_conv, {"target_db": "uniprot", "entry_ids": ["a", "b", "c", "d",
                                                                             "e", "f", "g", "h", "i", "j", "k"]})]:
            with self.subTest(tool=func.__name__), self.assertRaises(ValueError):
                await func(**args)

    async def test_api_error(self):
        with self.mock_http(lambda req: httpx.Response(404)), \
                patch("common.http.asyncio.sleep", new_callable=AsyncMock):
            with self.assertRaises(httpx.HTTPStatusError):
                await server.kegg_get(["map99999"])
