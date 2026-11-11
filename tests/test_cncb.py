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

    async def test_business_errors_and_malformed_payloads_are_not_zero_hits(self):
        payloads = [{"code": "500", "message": "Failed"}, {"code": "500", **_payload([]), "success": False},
                    {"code": "200", "result": None}, {"code": "200", "result": {"data": {"data": "bad"}}},
                    {"code": "200", "result": {"data": {"data": [], "recordsFiltered": -1}}}]
        for payload in payloads:
            with self.subTest(payload=payload), self.mock_http(lambda req: httpx.Response(200, json=payload)):
                with self.assertRaises((ValueError, RuntimeError)):
                    await server.cncb_search("rice")
        with self.mock_http(lambda req: httpx.Response(200, json=_payload([]))):
            result = await server.cncb_search("not found")
        self.assertEqual(result["count"], 0)
        self.assertEqual(result["records"], [])
