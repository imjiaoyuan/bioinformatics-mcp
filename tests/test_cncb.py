import json

import httpx

from servers.cncb_mcp import server
from tests.helpers import HTTPTestCase


def _payload(rows):
    return {"code": "200", "message": "Success!",
            "result": {"data": {"recordsTotal": len(rows), "recordsFiltered": len(rows),
                                "data": rows}}}


class CNCBTests(HTTPTestCase):
    async def test_search_gsa_records(self):
        rows = [{"id": "CRA024741", "type": "GSA", "title": "RNA-seq of indica rice",
                 "url": "https://ngdc.cncb.ac.cn/gsa/browse/CRA024741", "dbId": "gsa"}]

        def handler(req):
            self.assertIn("/search/api/specific", req.url.path)
            self.assertEqual(req.url.params["db"], "gsa")
            self.assertEqual(req.url.params["q"], "rice")
            self.assertEqual(req.url.params["length"], "5")
            return httpx.Response(200, text=json.dumps(_payload(rows)))

        with self.mock_http(handler):
            result = await server.cncb_search("rice", database="gsa", limit=5)
        self.assertEqual(result["count"], 1)
        self.assertEqual(result["records"][0]["id"], "CRA024741")
        self.assertTrue(result["records"][0]["url"].startswith("https://"))

    async def test_search_validation(self):
        with self.assertRaises(ValueError):
            await server.cncb_search("")
        with self.assertRaises(ValueError):
            await server.cncb_search("rice", database="pinterest")
        with self.assertRaises(ValueError):
            await server.cncb_search("rice", limit=0)

    async def test_search_api_error_not_silenced(self):
        with self.mock_http(lambda req: httpx.Response(500)):
            with self.assertRaises(httpx.HTTPStatusError):
                await server.cncb_search("rice")
