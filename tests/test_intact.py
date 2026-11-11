"""Mocked tests for the IntAct MCP api."""
from unittest.mock import AsyncMock, patch

import httpx

from servers.intact_mcp import api
from tests.helpers import HTTPTestCase


class IntActTests(HTTPTestCase):
    async def test_search_and_details(self):
        paths = []

        def handler(req):
            paths.append(req.url.path)
            if "findInteractor" in req.url.path:
                self.assertEqual(req.url.params["first"], "5")
                self.assertEqual(req.url.params["number"], "10")
                return httpx.Response(200, json={"content": [{"interactorAc": "EBI-366083", "interactorName": "TP53",
                                                              "interactorPreferredIdentifier": "P04637",
                                                              "interactorType": "protein"}], "totalElements": 1})
            if "(pubmed)" in req.url.path:
                return httpx.Response(200, json={"content": [{"ac": "EBI-10095907", "documentType": "interaction"}],
                                                 "totalElements": 1})
            if "EBI-4486632" in req.url.path:
                self.assertEqual(req.url.params["first"], "0")
                return httpx.Response(200, json={"content": [
                    {"ac": "EBI-4486632", "intactMiscore": 0.37, "confidenceValues": ["intact-miscore:0.37"],
                     "typeMIIdentifier": "MI:0915", "detectionMethod": "two hybrid array",
                     "detectionMethodMIIdentifier": "MI:0397", "experimentalRoleA": "bait",
                     "experimentalRoleB": "prey", "taxIdA": 3702, "taxIdB": 3702, "publicationPubmedIdentifier": None},
                    {"ac": "EBI-9999999", "intactMiscore": 0.1}], "totalElements": 2})
            return httpx.Response(200, json={"content": [{"ac": "EBI-16167654", "idA": "Q61221-1 (uniprotkb)",
                                                          "idB": "P53762 (uniprotkb)"}], "totalElements": 55})

        with self.mock_http(handler), patch("common.http.asyncio.sleep", new_callable=AsyncMock):
            search = await api.intact_interaction_search("brca1", limit=10, offset=5)
            self.assertEqual(search["content"][0]["idA"], "Q61221-1 (uniprotkb)")
            self.assertEqual(search["totalElements"], 55)
            self.assertIn("source_url", search)
            interactor = (await api.intact_interactor_search("p53", limit=10, offset=5))["content"][0]
            self.assertEqual(interactor["interactorPreferredIdentifier"], "P04637")
            details = await api.intact_interaction_details("ebi-4486632")
            self.assertEqual(details["interaction"]["intactMiscore"], 0.37)
            self.assertEqual(details["interaction"]["detectionMethodMIIdentifier"], "MI:0397")
            self.assertEqual(details["interaction"]["experimentalRoleB"], "prey")
            pub = (await api.intact_publication_interactions("11430896"))["content"][0]
            self.assertEqual(pub["ac"], "EBI-10095907")
        self.assertIn("/intact/ws/interaction/findInteractions/EBI-4486632", paths)

    async def test_details_unknown_ac(self):
        with self.mock_http(lambda req: httpx.Response(200, json={"content": [], "totalElements": 0})), \
                patch("common.http.asyncio.sleep", new_callable=AsyncMock):
            with self.assertRaises(ValueError):
                await api.intact_interaction_details("EBI-1")

    async def test_validation_all_tools(self):
        for func, args in [(api.intact_interaction_search, {"query": ""}),
                           (api.intact_interactor_search, {"query": "a b\nc"}),
                           (api.intact_interaction_details, {"interaction_ac": "bad ac"}),
                           (api.intact_interaction_details, {"interaction_ac": "Q04637"}),
                           (api.intact_publication_interactions, {"pubmed_id": "abc"}),
                           (api.intact_publication_interactions, {"pubmed_id": "11430896", "limit": 101})]:
            with self.subTest(tool=func.__name__), self.assertRaises(ValueError):
                await func(**args)

    async def test_api_error(self):
        with self.mock_http(lambda req: httpx.Response(404)):
            with self.assertRaises(httpx.HTTPStatusError):
                await api.intact_interaction_search("../bad")
