from unittest.mock import AsyncMock, patch

import httpx

from servers.gwas_mcp import server
from tests.helpers import HTTPTestCase


class GWASTests(HTTPTestCase):
    async def test_v2_filters_hal_pagination_and_study_links(self):
        requests = []
        def handler(req):
            requests.append(req)
            self.assertTrue(req.url.path.startswith("/gwas/rest/api/v2/"))
            return httpx.Response(200, json={"_embedded": {"studies": []}, "_links": {"next": {"href": "next"}},
                                            "page": {"totalElements": 5}, "full_summary_stats": "https://example.org/stats"})
        with self.mock_http(handler), patch("common.http.asyncio.sleep", new_callable=AsyncMock):
            for call in [server.gwas_traits("asthma"), server.gwas_studies(efo_id="EFO_0000270", ancestral_group="European"),
                         server.gwas_study("GCST1"), server.gwas_associations(rs_id="rs123", show_child_traits=True),
                         server.gwas_variant("rs123")]:
                result = await call
                self.assertEqual(result["_links"]["next"]["href"], "next")
                self.assertIn("full_summary_stats", result)
        self.assertEqual(requests[1].url.params["ancestral_group"], "European")
        self.assertEqual(requests[3].url.params["show_child_trait"], "true")
        self.assertEqual(requests[3].url.params["extended_geneset"], "false")

    async def test_validation_all_tools(self):
        for func, args in [(server.gwas_traits, {"query": ""}), (server.gwas_studies, {"page": -1}),
                           (server.gwas_study, {"accession": "bad"}), (server.gwas_associations, {}),
                           (server.gwas_variant, {"rs_id": "../"})]:
            with self.subTest(tool=func.__name__), self.assertRaises(ValueError):
                await func(**args)

    async def test_rate_limit_error(self):
        with self.mock_http(lambda req: httpx.Response(429)), patch("common.http.asyncio.sleep", new_callable=AsyncMock):
            with self.assertRaises(httpx.HTTPStatusError):
                await server.gwas_studies()
