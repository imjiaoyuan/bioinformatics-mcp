from unittest.mock import AsyncMock, patch

import httpx

from servers.ncbi_mcp import server
from tests.helpers import HTTPTestCase


class GEOTests(HTTPTestCase):
    async def test_search_summaries(self):
        with patch.object(server, "ncbi_search", AsyncMock(return_value={"ids": ["1"]})) as search, \
             patch.object(server, "ncbi_summary", AsyncMock(return_value={"result": {"1": {"accession": "GSE1"}}})):
            result = await server.geo_search("rice", 2)
            search.assert_awaited_once_with("gds", "rice", 2)
            self.assertEqual(result["summaries"]["1"]["accession"], "GSE1")

    async def test_record_characteristics(self):
        with self.mock_http(lambda req: httpx.Response(200, text="!Sample_characteristics_ch1 = treatment: heat\n!Sample_title = leaf")):
            self.assertEqual((await server.geo_record("GSM1"))["metadata"]["Sample_characteristics_ch1"], ["treatment: heat"])

    async def test_files_actual_links_and_bounds(self):
        def handler(req):
            self.assertIn("GSE1nnn/GSE1234", req.url.path)
            return httpx.Response(200, text='<a href="../">parent</a><a href="a.txt.gz">a</a><a href="b.txt.gz">b</a>')
        with self.mock_http(handler):
            result = await server.geo_files("GSE1234", 1)
            self.assertEqual(len(result["files"]), 1)
            self.assertTrue(result["truncated"])

    async def test_validation(self):
        for function, arguments in [(server.geo_search, {"query": ""}),
                                    (server.geo_record, {"accession": "../../etc"}),
                                    (server.geo_files, {"accession": "GSE1", "limit": 0})]:
            with self.subTest(tool=function.__name__), self.assertRaises(ValueError):
                await function(**arguments)

    async def test_api_failure_not_silenced(self):
        with self.mock_http(lambda req: httpx.Response(500)):
            with self.assertRaises(httpx.HTTPStatusError):
                await server.geo_record("GSE1")
