import httpx
from unittest.mock import AsyncMock, patch

from servers.hpo_mcp import server
from tests.helpers import HTTPTestCase


TERM = {"id": "HP:0001166", "name": "Arachnodactyly",
        "definition": "Abnormally long and slender fingers (spider fingers).",
        "synonyms": ["Spider fingers"], "xrefs": [], "publicationReferences": [],
        "descendantCount": 0, "translations": []}
SIMPLE = {"id": "HP:0000098", "name": "Short stature", "descendantCount": 3}


class HPOTests(HTTPTestCase):
    async def test_all_tools_success(self):
        def handler(req):
            self.assertEqual(req.url.host, "ontology.jax.org")
            path, params = req.url.path, req.url.params
            if path == "/api/hp/search":
                self.assertEqual(params["q"], "arachnodactyly")
                self.assertEqual(params["page"], "2")
                self.assertEqual(params["limit"], "1")
                return httpx.Response(200, json={"terms": [TERM], "totalCount": 5})
            if path == "/api/hp/terms":
                self.assertEqual(params["filter"], "HP:0001166,HP:0001519")
                return httpx.Response(200, json=[TERM, TERM])
            if path == "/api/hp/terms/HP:0001166":
                return httpx.Response(200, json=TERM)
            if path.endswith("/children"):
                return httpx.Response(200, json=[SIMPLE])
            if path.endswith("/parents"):
                return httpx.Response(200, json=[SIMPLE])
            if path.endswith("/ancestors"):
                return httpx.Response(200, json=[SIMPLE, SIMPLE])
            if path.endswith("/descendants"):
                return httpx.Response(200, json=[])
            raise AssertionError(path)

        with self.mock_http(handler), patch("common.http.asyncio.sleep", new_callable=AsyncMock):
            search = await server.hpo_search("arachnodactyly", limit=1, page=2)
            self.assertEqual(search["source_url"], "https://ontology.jax.org/api/hp/search?q=arachnodactyly&page=2&limit=1")
            self.assertEqual(search["terms"][0]["id"], "HP:0001166")
            self.assertEqual(search["totalCount"], 5)
            term = await server.hpo_term("hp:0001166")
            self.assertEqual(term["name"], "Arachnodactyly")
            self.assertEqual((await server.hpo_terms(["HP:0001166", "HP:0001519"]))["total"], 2)
            for tool in [server.hpo_children, server.hpo_parents]:
                result = await tool("HP:0001166")
                self.assertEqual(result["results"][0]["id"], "HP:0000098")
                self.assertEqual(result["pagination"], "local")
            self.assertEqual((await server.hpo_ancestors("HP:0001166"))["total"], 2)
            self.assertEqual((await server.hpo_descendants("HP:0001166"))["results"], [])

    async def test_validation_all_tools(self):
        bad_id = {"term_id": "bad"}
        for func, args in [(server.hpo_search, {"query": "ab"}),
                           (server.hpo_search, {"query": "x" * 251}),
                           (server.hpo_search, {"query": "marfan; drop"}),
                           (server.hpo_search, {"query": "marfan", "limit": 101}),
                           (server.hpo_term, bad_id),
                           (server.hpo_terms, {"term_ids": []}),
                           (server.hpo_terms, {"term_ids": ["HP:1"]}),
                           (server.hpo_terms, {"term_ids": ["HP:0001166"] * 101}),
                           (server.hpo_children, bad_id),
                           (server.hpo_parents, bad_id),
                           (server.hpo_ancestors, bad_id),
                           (server.hpo_descendants, bad_id)]:
            with self.subTest(tool=func.__name__), self.assertRaises(ValueError):
                await func(**args)

    async def test_term_not_found(self):
        with self.mock_http(lambda req: httpx.Response(200, json=None)), \
                patch("common.http.asyncio.sleep", new_callable=AsyncMock):
            with self.assertRaises(ValueError):
                await server.hpo_term("HP:9999999")

    async def test_api_error(self):
        with self.mock_http(lambda req: httpx.Response(404)), \
                patch("common.http.asyncio.sleep", new_callable=AsyncMock):
            with self.assertRaises(httpx.HTTPStatusError):
                await server.hpo_term("HP:0001166")
