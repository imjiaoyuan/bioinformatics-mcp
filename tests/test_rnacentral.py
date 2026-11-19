"""Mocked tests for the RNAcentral MCP api."""
import httpx

from servers.rnacentral_mcp import api
from tests.helpers import HTTPTestCase

ENTRY = {"rnacentral_id": "URS000075800A", "description": "HBB protein CDS", "sequence": "AUGGUGCAG",
         "length": 9, "rna_type": "misc_RNA", "md5": "abc", "count_distinct_organisms": 1,
         "distinct_databases": ["Ensembl"], "distinct_organisms": ["Homo sapiens"],
         "is_active": True, "publications": [], "url": "https://rnacentral.org/entry/URS000075800A",
         "xrefs": []}
PUBLICATIONS = {"count": 2, "next": None, "previous": None, "results": [
    {"title": "A study", "authors": ["A. Author"], "publication": "J. Biol. 2020", "pubmed_id": "12345678"},
    {"title": "Another", "authors": ["B. Author"], "publication": "RNA 2021", "doi": "10.1/x"}]}
SEARCH = {"hitCount": 250454, "entries": [{"id": "URS00007681C7_9606", "source": "rnacentral"},
                                          {"id": "URS00007E4AF8_10090", "source": "rnacentral"}]}


class RNAcentralTests(HTTPTestCase):
    async def test_search_entry_sequence_and_publications(self):
        paths = []

        def handler(req):
            paths.append((req.url.host, req.url.path, dict(req.url.params)))
            if "/ebisearch/" in req.url.path:
                self.assertEqual(req.url.params["query"], "miRNA")
                self.assertEqual(req.url.params["size"], "2")
                self.assertEqual(req.url.params["start"], "4")
                return httpx.Response(200, json=SEARCH)
            if req.url.path.endswith("/rna/URS000075800A"):
                return httpx.Response(200, json=ENTRY)
            if req.url.path.endswith("/publications"):
                return httpx.Response(200, json=PUBLICATIONS)
            raise AssertionError(f"unexpected path: {req.url.path}")

        with self.mock_http(handler):
            search = await api.rnacentral_search("miRNA", limit=2, offset=4)
            self.assertEqual(search["hit_count"], 250454)
            self.assertEqual([hit["urs"] for hit in search["results"]],
                             ["URS00007681C7", "URS00007E4AF8"])
            self.assertTrue(search["truncated"])
            entry = await api.rnacentral_entry("urs000075800a")
            self.assertEqual(entry["rna_type"], "misc_RNA")
            sequence = await api.rnacentral_sequence("URS000075800A")
            self.assertEqual(sequence["sequence"], "AUGGUGCAG")
            self.assertNotIn("md5", sequence)
            self.assertEqual(sequence["entry_url"], ENTRY["url"])
            publications = await api.rnacentral_publications("URS000075800A", limit=1)
            self.assertEqual(publications["total"], 2)
            self.assertEqual(len(publications["results"]), 1)
            self.assertTrue(publications["truncated"])
            self.assertEqual(publications["pagination"], "local")
        self.assertEqual(len(paths), 4)

    async def test_unexpected_entry_payload_is_rejected(self):
        with self.mock_http(lambda req: httpx.Response(200, json=["not-an-entry"])):
            with self.assertRaises(ValueError):
                await api.rnacentral_entry("URS000075800A")

    async def test_validation_before_network(self):
        cases = [(api.rnacentral_search, {"query": ""}),
                 (api.rnacentral_search, {"query": "x" * 301}),
                 (api.rnacentral_search, {"query": "mirna", "limit": 0}),
                 (api.rnacentral_entry, {"urs": "bad"}),
                 (api.rnacentral_entry, {"urs": "URS000075800"}),
                 (api.rnacentral_sequence, {"urs": "URS000075800A1"}),
                 (api.rnacentral_publications, {"urs": "ENSG000001"}),
                 (api.rnacentral_publications, {"urs": "URS000075800A", "limit": 101})]
        for func, kwargs in cases:
            with self.subTest(tool=func.__name__, kwargs=kwargs), self.assertRaises(ValueError):
                await func(**kwargs)

    async def test_api_error(self):
        with self.mock_http(lambda req: httpx.Response(500)):
            with self.assertRaises(httpx.HTTPStatusError):
                await api.rnacentral_entry("URS000075800A")
