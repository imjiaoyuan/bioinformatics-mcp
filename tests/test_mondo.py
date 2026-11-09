import asyncio
from unittest.mock import AsyncMock, patch

import httpx

from servers.mondo_mcp import server
from tests.helpers import HTTPTestCase


def _ontology():
    return {
        "graphs": [
            {
                "nodes": [
                    {"id": "http://purl.obolibrary.org/obo/MONDO_0005148", "type": "CLASS",
                     "lbl": "type 2 diabetes mellitus",
                     "meta": {
                         "definition": {"val": "A diabetes mellitus characterized by insulin resistance.",
                                        "xrefs": ["NCIT:P378", "GARD:0006080"]},
                         "synonyms": [
                             {"val": "T2D", "pred": "hasExactSynonym"},
                             {"val": "NIDDM", "pred": "hasExactSynonym"},
                         ],
                         "xrefs": [{"val": "OMIM:125853"}, {"val": "DOID:9352"},
                                   {"val": "MESH:D003924"}],
                         "subsets": ["otar"],
                     }},
                    {"id": "http://purl.obolibrary.org/obo/MONDO_0008383", "type": "CLASS",
                     "lbl": "retinitis pigmentosa",
                     "meta": {"xrefs": [{"val": "OMIM:268000"}]}},
                    {"id": "http://purl.obolibrary.org/obo/MONDO_0020182", "type": "CLASS",
                     "lbl": "obsolete historic disease",
                     "meta": {"deprecated": True}},
                ],
                "edges": [
                    {"sub": "http://purl.obolibrary.org/obo/MONDO_0005148",
                     "pred": "is_a",
                     "obj": "http://purl.obolibrary.org/obo/MONDO_0005010"},
                    {"sub": "http://purl.obolibrary.org/obo/MONDO_0008383",
                     "pred": "is_a",
                     "obj": "http://purl.obolibrary.org/obo/MONDO_0005148"},
                ],
            }
        ]
    }


class MondoTests(HTTPTestCase):
    def setUp(self):
        super().setUp()
        server._ontology = None
        server._lock = asyncio.Lock()

    async def test_tools_against_snapshot(self):
        def handler(req):
            self.assertEqual(req.url.path, "/obo/mondo.json")
            return httpx.Response(200, json=_ontology())
        with self.mock_http(handler), patch("common.http.asyncio.sleep", new_callable=AsyncMock):
            search = await server.mondo_search("niddm")
            self.assertEqual(search["results"][0]["mondo_id"], "MONDO:0005148")
            self.assertEqual(search["results"][0]["matched_in"], "synonym")
            self.assertEqual(search["results"][0]["matched_synonyms"], ["NIDDM"])
            self.assertTrue(search["pagination"] == "local" and search["total"] == 1)
            entry = await server.mondo_entry("mondo:0005148")
            self.assertEqual(entry["label"], "type 2 diabetes mellitus")
            self.assertIn("insulin resistance", entry["definition"])
            self.assertEqual(entry["definition_xrefs"], ["GARD:0006080", "NCIT:P378"])
            self.assertIn("OMIM:125853", entry["xrefs"])
            self.assertEqual(entry["subsets"], ["otar"])
            xrefs = await server.mondo_xrefs("MONDO:0005148")
            self.assertEqual(xrefs["xrefs"], ["DOID:9352", "MESH:D003924", "OMIM:125853"])
            self.assertEqual(xrefs["total"], 3)
            lookup = await server.mondo_xref_lookup("omim:125853")
            self.assertEqual(lookup["results"], [{"mondo_id": "MONDO:0005148",
                                                  "label": "type 2 diabetes mellitus"}])
            children = await server.mondo_children("MONDO:0005148")
            self.assertEqual(children["results"], [{"mondo_id": "MONDO:0008383",
                                                    "label": "retinitis pigmentosa"}])
            obsolete = await server.mondo_entry("MONDO:0020182")
            self.assertTrue(obsolete["obsolete"])

    async def test_validation_all_tools(self):
        with self.mock_http(lambda req: httpx.Response(200, json=_ontology())), \
                patch("common.http.asyncio.sleep", new_callable=AsyncMock):
            for func, args in [(server.mondo_search, {"query": ""}),
                               (server.mondo_search, {"query": "x", "limit": 0}),
                               (server.mondo_entry, {"mondo_id": "DOID:9352"}),
                               (server.mondo_entry, {"mondo_id": "MONDO:0000001"}),
                               (server.mondo_xrefs, {"mondo_id": "bad"}),
                               (server.mondo_xref_lookup, {"xref": "OMIM 125853"}),
                               (server.mondo_xref_lookup, {"xref": "OMIM:125853", "offset": -1}),
                               (server.mondo_children, {"mondo_id": "MONDO:123"})]:
                with self.subTest(tool=func.__name__), self.assertRaises(ValueError):
                    await func(**args)

    async def test_api_error(self):
        with self.mock_http(lambda req: httpx.Response(404)):
            with self.assertRaises(httpx.HTTPStatusError):
                await server.mondo_entry("MONDO:0005148")
