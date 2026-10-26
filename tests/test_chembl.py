from unittest.mock import AsyncMock, patch

import httpx

from servers.chembl_mcp import server
from tests.helpers import HTTPTestCase


class ChEMBLTests(HTTPTestCase):
    async def test_search_and_records(self):
        paths = []
        def handler(req):
            paths.append(req.url.path)
            if "/search" in req.url.path:
                self.assertEqual(req.url.params["offset"], "1")
                return httpx.Response(200, json={"page_meta": {"total_count": 2, "next": "next"}, "molecules": [{"molecule_chembl_id": "CHEMBL25"}]})
            return httpx.Response(200, json={"id": "CHEMBL25"})
        with self.mock_http(handler), patch("common.http.asyncio.sleep", new_callable=AsyncMock):
            self.assertEqual((await server.chembl_search("aspirin", offset=1))["page_meta"]["next"], "next")
            for tool in [server.chembl_molecule, server.chembl_target, server.chembl_assay]:
                self.assertEqual((await tool("chembl25"))["id"], "CHEMBL25")
        self.assertIn("/chembl/api/data/assay/CHEMBL25.json", paths)

    async def test_activity_semantics_and_mechanisms(self):
        def handler(req):
            if "activity" in req.url.path:
                self.assertEqual(req.url.params["standard_type"], "IC50")
                self.assertEqual(req.url.params["target_chembl_id"], "CHEMBL1")
                return httpx.Response(200, json={"activities": [{"standard_type": "IC50", "standard_units": "nM", "standard_relation": "<", "standard_value": "10", "data_validity_comment": "Outside typical range"}]})
            self.assertEqual(req.url.params["molecule_chembl_id"], "CHEMBL25")
            return httpx.Response(200, json={"mechanisms": [], "page_meta": {"total_count": 0}})
        with self.mock_http(handler), patch("common.http.asyncio.sleep", new_callable=AsyncMock):
            activity = (await server.chembl_activities(target_id="CHEMBL1", standard_type="IC50"))["activities"][0]
            self.assertEqual(activity["standard_relation"], "<")
            self.assertEqual(activity["standard_units"], "nM")
            self.assertEqual((await server.chembl_mechanisms("CHEMBL25"))["mechanisms"], [])

    async def test_validation_all_tools(self):
        for func, args in [(server.chembl_search, {"query": "x", "resource": "bad"}),
                           (server.chembl_molecule, {"chembl_id": "bad"}), (server.chembl_target, {"chembl_id": "../"}),
                           (server.chembl_activities, {}), (server.chembl_assay, {"chembl_id": "bad"}),
                           (server.chembl_mechanisms, {"molecule_id": "CHEMBL1", "limit": 101})]:
            with self.subTest(tool=func.__name__), self.assertRaises(ValueError):
                await func(**args)

    async def test_api_error(self):
        with self.mock_http(lambda req: httpx.Response(404)):
            with self.assertRaises(httpx.HTTPStatusError):
                await server.chembl_molecule("CHEMBL99999999")
