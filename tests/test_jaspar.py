"""Mocked tests for the JASPAR MCP api."""
import httpx

from servers.jaspar_mcp import api
from tests.helpers import HTTPTestCase

LIST = {"count": 3, "next": "https://jaspar.elixir.no/api/v1/matrix/?name=TP53&page=2&page_size=1",
        "previous": None, "results": [
            {"matrix_id": "MA0049.1", "base_id": "MA0049", "name": "hb", "collection": "CORE"},
            {"matrix_id": "MA0049.2", "base_id": "MA0049", "name": "TP53", "collection": "CORE"}]}
DETAIL = {"matrix_id": "MA0049.1", "base_id": "MA0049", "name": "hb", "collection": "CORE",
          "tax_group": "vertebrates", "species": ["taxon:9606"], "pfm": {"A": [1.0, 6.0], "C": [2.0, 1.0]},
          "pubmed_ids": ["1234"], "uniprot_ids": ["P04637"], "sequence_logo": "https://x/logo.png",
          "versions_url": "https://jaspar.elixir.no/api/v1/matrix/MA0049/", "type": "SELEX"}


class JasparTests(HTTPTestCase):
    async def test_search_and_matrix(self):
        seen = []

        def handler(req):
            seen.append((req.url.path, dict(req.url.params)))
            if req.url.path.endswith("/matrix/"):
                self.assertEqual(req.url.params["search"], "TP53")
                self.assertEqual(req.url.params["tax_group"], "vertebrates")
                self.assertEqual(req.url.params["collection"], "CORE")
                self.assertEqual(req.url.params["page_size"], "1")
                self.assertEqual(req.url.params["page"], "2")
                return httpx.Response(200, json={**LIST, "results": LIST["results"][1:]})
            if req.url.path.endswith("/matrix/MA0049/"):
                return httpx.Response(200, json=DETAIL)
            raise AssertionError(f"unexpected path: {req.url.path}")

        with self.mock_http(handler):
            search = await api.jaspar_search("TP53", tax_group="vertebrates", collection="CORE",
                                             limit=1, offset=1)
            self.assertEqual(search["results"][0]["matrix_id"], "MA0049.2")
            self.assertEqual(search["total"], 3)
            self.assertTrue(search["truncated"])
            matrix = await api.jaspar_matrix("ma0049")
            self.assertEqual(matrix["name"], "hb")
            self.assertEqual(matrix["pfm"]["A"], [1.0, 6.0])
            self.assertIn("https://jaspar.elixir.no/api/v1/matrix/MA0049/", matrix["source_url"])
        self.assertEqual(len(seen), 2)

    async def test_missing_matrix_is_an_error(self):
        with self.mock_http(lambda req: httpx.Response(200, json={"detail": "Not found."})):
            with self.assertRaises(ValueError):
                await api.jaspar_matrix("MA9999")

    async def test_validation_before_network(self):
        cases = [(api.jaspar_search, {"search": "x" * 201}),
                 (api.jaspar_search, {"search": "TP53", "tax_group": "Vertebrates!"}),
                 (api.jaspar_search, {"search": "TP53", "collection": "core;"}),
                 (api.jaspar_search, {"search": "TP53", "limit": 0}),
                 (api.jaspar_matrix, {"matrix_id": "bad"}),
                 (api.jaspar_matrix, {"matrix_id": "MX0049"}),
                 (api.jaspar_matrix, {"matrix_id": "MA0049.3.1"})]
        for func, kwargs in cases:
            with self.subTest(tool=func.__name__, kwargs=kwargs), self.assertRaises(ValueError):
                await func(**kwargs)

    async def test_api_error(self):
        with self.mock_http(lambda req: httpx.Response(503)):
            with self.assertRaises(httpx.HTTPStatusError):
                await api.jaspar_matrix("MA0049")
