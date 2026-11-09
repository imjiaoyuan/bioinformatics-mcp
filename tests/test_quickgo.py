import httpx
from unittest.mock import AsyncMock, patch

from servers.quickgo_mcp import server
from tests.helpers import HTTPTestCase


def _term(go_id, ancestors=None):
    return {"id": go_id, "isObsolete": False, "name": "term " + go_id, "aspect": "biological_process",
            "definition": {"text": "def"}, "ancestors": ancestors or []}


def _handler(req, paths):
    paths.append(req.url.path)
    params = req.url.params
    if req.url.path.endswith("/search") and "/annotation/" in req.url.path:
        assert params["geneProductId"] == "UniProtKB:P12345"
        assert params["page"] == "2" and params["limit"] == "3"
        return httpx.Response(200, json={"numberOfHits": 16, "results": [{"id": "UniProtKB:P12345!1", "goId": "GO:0003824",
                                                 "goAspect": "molecular_function", "qualifier": "enables"}],
                             "pageInfo": {"resultsPerPage": 3, "current": 2, "total": 6}})
    if req.url.path.endswith("/search"):
        assert params["query"] == "apoptosome" and params["limit"] == "20"
        return httpx.Response(200, json={"numberOfHits": 1, "results": [_term("GO:0043293")],
                             "pageInfo": {"resultsPerPage": 20, "current": 1, "total": 1}})
    if req.url.path.endswith("/ancestors"):
        assert params["relation"] == "isa,part_of"
        return httpx.Response(200, json={"numberOfHits": 2, "results": [
            _term("GO:0006915", ["GO:0008150", "GO:0008219", "GO:0012501"]),
            _term("GO:0006955")]})
    ids = req.url.path.rsplit("/", 1)[-1].split(",")
    return httpx.Response(200, json={"numberOfHits": len(ids), "results": [_term(i) for i in ids], "pageInfo": None})


class QuickGoTests(HTTPTestCase):
    async def test_all_tools_success(self):
        paths: list[str] = []
        with self.mock_http(lambda req: _handler(req, paths)), \
                patch("common.http.asyncio.sleep", new_callable=AsyncMock):
            term = await server.quickgo_go_term(["go:0006915"])
            self.assertEqual(term["results"][0]["id"], "GO:0006915")
            self.assertTrue(term["source_url"].endswith("/ontology/go/terms/GO:0006915"))

            search = await server.quickgo_go_search("apoptosome")
            self.assertEqual(search["results"][0]["id"], "GO:0043293")

            ann = await server.quickgo_annotations("UniProtKB:P12345", limit=3, offset=3)
            self.assertEqual(ann["pageInfo"]["current"], 2)
            self.assertEqual(ann["results"][0]["goId"], "GO:0003824")
            self.assertTrue(ann["source_url"].startswith("https://www.ebi.ac.uk/QuickGO/services/annotation/search"))

            slim = await server.quickgo_slim(["GO:0006915", "GO:0006955"], ["GO:0008150", "GO:0006955"])
            rows = {row["term"]: row for row in slim["results"]}
            self.assertEqual(rows["GO:0006915"]["slim_id"], "GO:0008150")
            self.assertFalse(rows["GO:0006915"]["direct"])
            self.assertEqual(rows["GO:0006955"]["slim_id"], "GO:0006955")
            self.assertTrue(rows["GO:0006955"]["direct"])
            self.assertEqual(slim["pagination"], "local")
            self.assertTrue("/ontology/go/terms/GO:0006915,GO:0006955/ancestors" in slim["source_url"])
        self.assertEqual(len(paths), 4)

    async def test_annotations_filters(self):
        seen = {}
        def handler(req):
            seen.update(req.url.params)
            return httpx.Response(200, json={"numberOfHits": 0, "results": [], "pageInfo": {"resultsPerPage": 20, "current": 1, "total": 0}})
        with self.mock_http(handler), patch("common.http.asyncio.sleep", new_callable=AsyncMock):
            await server.quickgo_annotations("P12345", go_id="GO:0006915", aspect="biological_process")
        self.assertEqual(seen["goId"], "GO:0006915")
        self.assertEqual(seen["aspect"], "biological_process")

    async def test_validation_all_tools(self):
        for func, args in [(server.quickgo_go_term, {"go_ids": ["GO:6915"]}),
                           (server.quickgo_go_term, {"go_ids": []}),
                           (server.quickgo_go_term, {"go_ids": ["CHEMBL25"]}),
                           (server.quickgo_go_search, {"query": "  "}),
                           (server.quickgo_go_search, {"query": "ok", "limit": 0}),
                           (server.quickgo_annotations, {"gene_product_id": "bad id!"}),
                           (server.quickgo_annotations, {"gene_product_id": "P12345", "go_id": "GO:1"}),
                           (server.quickgo_annotations, {"gene_product_id": "P12345", "aspect": "cheese"}),
                           (server.quickgo_annotations, {"gene_product_id": "P12345", "limit": 101}),
                           (server.quickgo_annotations, {"gene_product_id": "P12345", "limit": 10, "offset": 5}),
                           (server.quickgo_slim, {"go_ids": ["GO:0006915"], "slim_ids": []}),
                           (server.quickgo_slim, {"go_ids": ["GO:0006915"], "slim_ids": ["GO:0008150"], "relation": "regulates"})]:
            with self.subTest(tool=func.__name__), self.assertRaises(ValueError):
                await func(**args)

    async def test_api_error(self):
        with self.mock_http(lambda req: httpx.Response(404)), \
                patch("common.http.asyncio.sleep", new_callable=AsyncMock):
            with self.assertRaises(httpx.HTTPStatusError):
                await server.quickgo_go_term(["GO:9999999"])
