import json
from unittest.mock import AsyncMock, patch

import httpx

from servers.gdc_mcp import server
from tests.helpers import HTTPTestCase

UUID = "ead53b27-6ad9-4b96-b5d4-0d4f06fb2d13"


class GDCTests(HTTPTestCase):
    def setUp(self):
        super().setUp()
        self.sleep = patch("common.http.asyncio.sleep", new_callable=AsyncMock)
        self.sleep.start()
        self.addCleanup(self.sleep.stop)

    async def test_search_filters_fields_and_pagination(self):
        seen = []
        def handler(req):
            seen.append(req)
            self.assertEqual(req.url.params["size"], "1")
            self.assertEqual(req.url.params["from"], "2")
            self.assertTrue(req.url.params["fields"])
            self.assertTrue(json.loads(req.url.params["filters"])["content"])
            return httpx.Response(200, json={"data": {"hits": [{"id": "one"}], "pagination": {"total": 5}}})
        with self.mock_http(handler):
            for call in [server.gdc_projects(limit=1, offset=2),
                         server.gdc_cases("TCGA-BRCA", limit=1, offset=2),
                         server.gdc_files("TCGA-BRCA", workflow="STAR - Counts", limit=1, offset=2)]:
                result = await call
                self.assertTrue(result["truncated"])
                self.assertEqual(result["total"], 5)
        filters = json.loads(seen[-1].url.params["filters"])["content"]
        self.assertIn({"op": "in", "content": {"field": "analysis.workflow_type", "value": ["STAR - Counts"]}}, filters)
        self.assertEqual(seen[1].url.params["expand"], "demographic,diagnoses,samples")
        self.assertNotIn("demographic", seen[1].url.params["fields"].split(","))

    async def test_file_and_open_download(self):
        with self.mock_http(lambda req: httpx.Response(200, json={"data": {"access": "open", "file_id": UUID}})):
            self.assertEqual((await server.gdc_file(UUID))["data"]["file_id"], UUID)
            self.assertEqual((await server.gdc_download_url(UUID))["download_url"], f"{server.BASE}/data/{UUID}")
        with self.mock_http(lambda req: httpx.Response(200, json={"data": {"access": "controlled"}})):
            with self.assertRaisesRegex(ValueError, "controlled"):
                await server.gdc_download_url(UUID)

    async def test_manifest_missing_and_deduplicated(self):
        missing = "00000000-0000-0000-0000-000000000000"
        def handler(req):
            filters = json.loads(req.url.params["filters"])
            self.assertEqual(len(filters["content"][0]["content"]["value"]), 2)
            return httpx.Response(200, json={"data": {"hits": [{"file_id": UUID, "file_name": "counts.tsv", "md5sum": "abc", "file_size": 42, "state": "released"}], "pagination": {"total": 1}}})
        with self.mock_http(handler):
            result = await server.gdc_manifest([UUID, UUID, missing])
        self.assertIn("id\tfilename\tmd5\tsize\tstate\n", result["manifest"])
        self.assertIn("counts.tsv\tabc\t42\treleased", result["manifest"])
        self.assertEqual(result["missing_ids"], [missing])

    async def test_validation_all_tools(self):
        for func, args in [(server.gdc_projects, {"limit": 0}), (server.gdc_cases, {"project_id": "../"}),
                           (server.gdc_files, {"project_id": "TCGA-BRCA", "access": "all"}),
                           (server.gdc_file, {"file_id": "bad"}), (server.gdc_manifest, {"file_ids": []}),
                           (server.gdc_download_url, {"file_id": "bad"})]:
            with self.subTest(tool=func.__name__), self.assertRaises(ValueError):
                await func(**args)

    async def test_rate_limit_and_empty(self):
        with self.mock_http(lambda req: httpx.Response(429)):
            with self.assertRaises(httpx.HTTPStatusError):
                await server.gdc_projects()
        with self.mock_http(lambda req: httpx.Response(200, json={"data": {"hits": [], "pagination": {"total": 0}}})):
            self.assertEqual((await server.gdc_projects())["results"], [])
