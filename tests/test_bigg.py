from unittest.mock import AsyncMock, patch

import httpx

from servers.bigg_mcp import api
from tests.helpers import HTTPTestCase


class BiGGTests(HTTPTestCase):
    async def test_all_tools_success(self):
        paths = []
        def handler(req):
            paths.append(req.url.path)
            if req.url.path == "/api/v2/models":
                return httpx.Response(200, json={"results_count": 2, "results": [
                    {"bigg_id": "e_coli_core", "organism": "Escherichia coli", "reaction_count": 95},
                    {"bigg_id": "iJO1366", "organism": "Escherichia coli", "reaction_count": 2583}]})
            if req.url.path == "/api/v2/models/e_coli_core":
                return httpx.Response(200, json={"bigg_id": "e_coli_core", "organism": "Escherichia coli",
                                                 "version": "1.5", "reaction_count": 95})
            if req.url.path == "/api/v2/models/e_coli_core/reactions":
                return httpx.Response(200, json={"results_count": 2, "results": [
                    {"bigg_id": "PGI", "name": "Glucose-6-phosphate isomerase"}]})
            if req.url.path == "/api/v2/models/e_coli_core/metabolites":
                return httpx.Response(200, json={"results_count": 1, "results": [
                    {"bigg_id": "g6p_c", "name": "D-Glucose 6-phosphate", "compartment_bigg_id": "c"}]})
            if req.url.path == "/api/v2/models/e_coli_core/reactions/PGI":
                return httpx.Response(200, json={"bigg_id": "PGI", "model_bigg_id": "e_coli_core",
                                                 "results": [{"reaction_string": "g6p_c <=> f6p_c",
                                                              "lower_bound": -1000.0, "upper_bound": 1000.0,
                                                              "gene_reaction_rule": "b4025"}]})
            if req.url.path == "/api/v2/models/e_coli_core/metabolites/g6p_c":
                return httpx.Response(200, json={"bigg_id": "g6p", "model_bigg_id": "e_coli_core",
                                                 "formula": "C6H11O9P", "compartment_bigg_id": "c",
                                                 "reactions": [{"bigg_id": "PGI"}]})
            if req.url.path == "/api/v2/search":
                self.assertEqual(req.url.params["query"], "ATPM")
                self.assertEqual(req.url.params["search_type"], "reactions")
                return httpx.Response(200, json={"results_count": 2, "results": [
                    {"bigg_id": "ATPM", "name": "ATP maintenance requirement", "model_bigg_id": "Universal"},
                    {"bigg_id": "ATPS", "name": "ATPase cytosolic", "model_bigg_id": "Universal"}]})
            self.fail(f"unexpected path {req.url.path}")
        with self.mock_http(handler), patch("common.http.asyncio.sleep", new_callable=AsyncMock):
            models = await api.bigg_models(limit=1, offset=1)
            self.assertEqual(models["results"][0]["bigg_id"], "iJO1366")
            self.assertEqual(models["total"], 2)
            self.assertFalse(models["truncated"])
            self.assertEqual(models["pagination"], "local")
            self.assertIn("source_url", models)
            self.assertEqual((await api.bigg_model("e_coli_core"))["version"], "1.5")
            self.assertEqual((await api.bigg_model_reactions("e_coli_core"))["results"][0]["bigg_id"], "PGI")
            self.assertEqual((await api.bigg_model_metabolites("e_coli_core"))["results"][0]["bigg_id"], "g6p_c")
            reaction = await api.bigg_reaction("e_coli_core", "PGI")
            self.assertEqual(reaction["results"][0]["reaction_string"], "g6p_c <=> f6p_c")
            metabolite = await api.bigg_metabolite("e_coli_core", "g6p_c")
            self.assertEqual(metabolite["formula"], "C6H11O9P")
            self.assertEqual((await api.bigg_search("ATPM"))["results"][0]["bigg_id"], "ATPM")
        self.assertIn("/api/v2/models/e_coli_core/reactions/PGI", paths)

    async def test_validation_all_tools(self):
        for func, kwargs in [(api.bigg_models, {"limit": 0}),
                             (api.bigg_model, {"model_bigg_id": "../x"}),
                             (api.bigg_model_reactions, {"model_bigg_id": "bad id"}),
                             (api.bigg_model_reactions, {"model_bigg_id": "e_coli_core", "limit": 101}),
                             (api.bigg_model_metabolites, {"model_bigg_id": ""}),
                             (api.bigg_reaction, {"model_bigg_id": "e_coli_core",
                                                     "reaction_bigg_id": "bad reaction"}),
                             (api.bigg_metabolite, {"model_bigg_id": "e_coli_core",
                                                       "metabolite_bigg_id": "a/b"}),
                             (api.bigg_search, {"query": "x", "search_type": "proteins"}),
                             (api.bigg_search, {"query": "   "})]:
            with self.subTest(tool=func.__name__), self.assertRaises(ValueError):
                await func(**kwargs)

    async def test_api_error(self):
        with self.mock_http(lambda req: httpx.Response(404)):
            with patch("common.http.asyncio.sleep", new_callable=AsyncMock):
                with self.assertRaises(httpx.HTTPStatusError):
                    await api.bigg_model("no_such_model")
