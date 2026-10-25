import json

import httpx

from servers.gprofiler_mcp import server
from tests.helpers import HTTPTestCase


class GProfilerTests(HTTPTestCase):
    async def test_enrichment_custom_background_and_bounds(self):
        def handler(req):
            body = json.loads(req.content)
            self.assertEqual(body["domain_scope"], "custom")
            self.assertEqual(body["background"], ["TP53", "MDM2"])
            self.assertEqual(body["sources"], ["GO:BP", "GO:MF", "GO:CC"])
            return httpx.Response(200, json={"result": [{"native": "GO:1"}] * 3, "meta": {"version": "test"}})
        with self.mock_http(handler):
            result = await server.gprofiler_enrichment(["TP53"], background=["TP53", "MDM2"], limit=1)
            self.assertEqual(len(result["result"]), 1)
            self.assertTrue(result["truncated"])
            self.assertEqual(result["meta"]["version"], "test")

    async def test_convert_and_orthologs(self):
        def handler(req):
            self.assertIn(json.loads(req.content)["target"], ["ENTREZGENE_ACC", "mmusculus"])
            return httpx.Response(200, json={"result": [{"incoming": "TP53", "converted": "7157"}]})
        with self.mock_http(handler):
            for func in (server.gprofiler_convert, server.gprofiler_orthologs):
                self.assertEqual((await func(["TP53"]))["result"][0]["incoming"], "TP53")

    async def test_all_tool_validation(self):
        for func in (server.gprofiler_enrichment, server.gprofiler_convert, server.gprofiler_orthologs):
            with self.subTest(tool=func.__name__), self.assertRaises(ValueError):
                await func([])
        with self.assertRaises(ValueError):
            await server.gprofiler_enrichment(["TP53"], threshold=float("nan"))
        with self.assertRaises(ValueError):
            await server.gprofiler_enrichment(["TP53"], sources=["invalid"])
        with self.assertRaises(ValueError):
            await server.gprofiler_convert(["TP53"], target="ENTREZGENE")

    async def test_api_failure(self):
        with self.mock_http(lambda req: httpx.Response(429)):
            with self.assertRaises(httpx.HTTPStatusError):
                await server.gprofiler_enrichment(["TP53"])
