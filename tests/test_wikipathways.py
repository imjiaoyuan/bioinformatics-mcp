"""Mocked tests for the WikiPathways MCP api."""
import httpx

from common import api as common_api
from servers.wikipathways_mcp import api
from tests.helpers import HTTPTestCase

PATHWAY_INFO = {"pathwayInfo": [
    {"id": "WP554", "url": "https://www.wikipathways.org/instance/WP554",
     "name": "Cytochrome P450 - arranged by substrate type", "species": "Homo sapiens",
     "revision": "2025-05-22", "authors": "MaintBot"},
    {"id": "WP10", "url": "https://www.wikipathways.org/instance/WP10",
     "name": "IL-9 signaling pathway", "species": "Mus musculus",
     "revision": "2025-07-10", "authors": "A.Pandey"},
    {"id": "WP23", "url": "https://www.wikipathways.org/instance/WP23",
     "name": "p53 pathway feedback branches", "species": "Homo sapiens",
     "revision": "2024-01-15", "authors": "Kdahlquist"}]}
ORGANISMS = {"organisms": [
    {"latin": "Homo_sapiens", "two-letter-code": "Hs", "common": "Human",
     "pathways": [{"id": "WP554", "url": "https://www.wikipathways.org/instance/WP554",
                   "name": "Cytochrome P450 - arranged by substrate type"}]},
    {"latin": "Mus_musculus", "two-letter-code": "Mm", "common": "Mouse",
     "pathways": [{"id": "WP10", "url": "https://www.wikipathways.org/instance/WP10",
                   "name": "IL-9 signaling pathway"}]}]}


class WikiPathwaysTests(HTTPTestCase):
    def setUp(self):
        super().setUp()
        common_api._cache.clear()

    def handler(self, req):
        if req.url.path.endswith("/findPathwaysByText.json"):
            return httpx.Response(200, json=PATHWAY_INFO)
        if req.url.path.endswith("/listPathways.json"):
            return httpx.Response(200, json=ORGANISMS)
        raise AssertionError(f"unexpected path: {req.url.path}")

    async def test_organisms_search_and_species_pathways(self):
        with self.mock_http(self.handler):
            organisms = await api.wikipathways_organisms()
            self.assertEqual(organisms["total"], 2)
            self.assertEqual(organisms["results"][0]["pathway_count"], 1)
            self.assertEqual(organisms["results"][0]["two_letter_code"], "Hs")
            search = await api.wikipathways_search("WP554")
            self.assertEqual(search["results"][0]["id"], "WP554")
            self.assertEqual(search["total"], 1)
            search = await api.wikipathways_search("pathway", species="Homo sapiens", limit=1)
            self.assertEqual(search["results"][0]["id"], "WP23")
            self.assertEqual(search["total"], 1)
            self.assertFalse(search["truncated"])
            pathways = await api.wikipathways_species_pathways("Homo_sapiens")
            self.assertEqual(pathways["total"], 1)
            self.assertEqual(pathways["results"][0]["name"], "Cytochrome P450 - arranged by substrate type")

    async def test_unknown_species_is_an_error(self):
        with self.mock_http(self.handler):
            with self.assertRaises(ValueError):
                await api.wikipathways_species_pathways("Drosophila melanogaster")

    async def test_validation_before_network(self):
        cases = [(api.wikipathways_search, {"query": ""}),
                 (api.wikipathways_search, {"query": "p53", "species": "Homo; sapiens"}),
                 (api.wikipathways_search, {"query": "p53", "limit": 0}),
                 (api.wikipathways_search, {"query": "p53", "offset": -1}),
                 (api.wikipathways_species_pathways, {"species": ""}),
                 (api.wikipathways_species_pathways, {"species": "a" * 101}),
                 (api.wikipathways_species_pathways, {"species": "Homo sapiens", "limit": 101})]
        for func, kwargs in cases:
            with self.subTest(tool=func.__name__, kwargs=kwargs), self.assertRaises(ValueError):
                await func(**kwargs)

    async def test_api_error(self):
        with self.mock_http(lambda req: httpx.Response(500)):
            with self.assertRaises(httpx.HTTPStatusError):
                await api.wikipathways_search("p53")
