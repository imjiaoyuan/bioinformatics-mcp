"""Mocked tests for the Open Tree of Life MCP api."""
import httpx

from servers.opentree_mcp import api
from tests.helpers import HTTPTestCase

MATCHES = {"context": "All life", "unmatched_names": ["Not a species"],
           "results": [{"matches": [{"search_string": "homo sapiens", "matched_name": "Homo sapiens",
                                     "is_synonym": False, "score": 1.0,
                                     "taxon": {"ott_id": 770315, "flags": [],
                                               "tax_sources": ["ncbi:9606", "gbif:2436436"]}}]}]}
NODE = {"node_id": "ott770315", "synth_id": "opentree19.4", "num_tips": 1, "terminal": True,
        "supported_by": ["ott770315"],
        "taxon": {"ott_id": 770315, "name": "Homo sapiens", "rank": "species",
                  "tax_sources": ["ncbi:9606"]}}
ABOUT = {"synth_id": "opentree19.4", "taxonomy_version": "ott3.10", "num_source_tree_ids": 230,
         "num_trees": 199, "num_tips": 74746, "num_studies": 137,
         "root_taxon_name": "cellular organisms", "generated_timestamp": "2025-01-01"}


class OpenTreeTests(HTTPTestCase):
    async def test_match_names_node_and_about(self):
        seen = []

        def handler(req):
            seen.append((req.url.path, req.read().decode()))
            if req.url.path.endswith("/tnrs/match_names"):
                self.assertIn('"names"', seen[-1][1])
                self.assertIn('"Pan troglodytes"', seen[-1][1])
                return httpx.Response(200, json=MATCHES)
            if req.url.path.endswith("/tree_of_life/node_info"):
                self.assertIn('"ott_id":770315', seen[-1][1])
                return httpx.Response(200, json=NODE)
            if req.url.path.endswith("/tree_of_life/about"):
                return httpx.Response(200, json=ABOUT)
            raise AssertionError(f"unexpected path: {req.url.path}")

        with self.mock_http(handler):
            matches = await api.opentree_match_names(["Homo sapiens", "Pan troglodytes", "Not a species"])
            self.assertEqual(matches["unmatched_names"], ["Not a species"])
            self.assertEqual(matches["results"][0]["ott_id"], 770315)
            self.assertEqual(matches["results"][0]["tax_sources"], ["ncbi:9606", "gbif:2436436"])
            node = await api.opentree_node("770315")
            self.assertEqual(node["name"], "Homo sapiens")
            self.assertEqual(node["rank"], "species")
            self.assertEqual(node["num_tips"], 1)
            about = await api.opentree_about()
            self.assertEqual(about["synth_id"], "opentree19.4")
            self.assertEqual(about["num_trees"], 199)
        self.assertEqual(len(seen), 3)

    async def test_unexpected_payload_is_an_error(self):
        with self.mock_http(lambda req: httpx.Response(200, json=["oops"])):
            with self.assertRaises(ValueError):
                await api.opentree_about()

    async def test_validation_before_network(self):
        cases = [(api.opentree_match_names, {"names": []}),
                 (api.opentree_match_names, {"names": ["Homo sapiens"] * 51}),
                 (api.opentree_match_names, {"names": ["a|b"]}),
                 (api.opentree_match_names, {"names": ["Homo sapiens"], "context": "x" * 61}),
                 (api.opentree_node, {"ott_id": "bad"}),
                 (api.opentree_node, {"ott_id": "770315.5"})]
        for func, kwargs in cases:
            with self.subTest(tool=func.__name__, kwargs=kwargs), self.assertRaises(ValueError):
                await func(**kwargs)

    async def test_api_error(self):
        with self.mock_http(lambda req: httpx.Response(500)):
            with self.assertRaises(httpx.HTTPStatusError):
                await api.opentree_node("770315")
