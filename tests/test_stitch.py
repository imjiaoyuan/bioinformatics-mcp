"""Mocked tests for the STITCH MCP api (stitch.embl.de is unreachable from CI)."""
import httpx

from servers.stitch_mcp import api
from tests.helpers import HTTPTestCase

RESOLVE = [{"preferredName": "TP53", "stringId": "9606.ENSP00000269305"},
           {"preferredName": "aspirin", "stringId": "CID0000002244"}]
NETWORK = [
    {"from": "TP53", "to": "aspirin", "score": "0.833", "type": "chemical-protein"},
    {"from": "TP53", "to": "MDM2", "score": "0.912", "type": "protein-protein"}]
ENRICHMENT = [{"category": "Process", "term": "apoptotic process", "number_of_genes": 4,
               "number_of_genes_in_background": 1000, "ncbiTaxonId": 9606, "inputGenes": "TP53",
               "preferredNames": "TP53", "p_value": 0.001, "fdr_value": 0.02, "description": "..."}]


class StitchTests(HTTPTestCase):
    async def test_resolve_interactions_and_enrichment(self):
        seen = []

        def handler(req):
            seen.append((req.url.path, dict(req.url.params)))
            if req.url.path.endswith("/get_string_ids"):
                self.assertEqual(req.url.params["identifiers"], "TP53\raspirin")
                self.assertEqual(req.url.params["species"], "9606")
                return httpx.Response(200, json=RESOLVE)
            if req.url.path.endswith("/network"):
                self.assertEqual(req.url.params["required_score"], "700")
                return httpx.Response(200, json=NETWORK)
            if req.url.path.endswith("/enrichment"):
                return httpx.Response(200, json=ENRICHMENT)
            raise AssertionError(f"unexpected path: {req.url.path}")

        with self.mock_http(handler):
            resolved = await api.stitch_resolve(["TP53", "aspirin"])
            self.assertEqual([row["stringId"] for row in resolved], [r["stringId"] for r in RESOLVE])
            interactions = await api.stitch_interactions(["TP53", "aspirin"], required_score=700, limit=1)
            self.assertEqual(len(interactions), 1)
            self.assertEqual(interactions[0]["to"], "aspirin")
            enrichment = await api.stitch_enrichment(["TP53"])
            self.assertEqual(enrichment[0]["term"], "apoptotic process")
        self.assertEqual(len(seen), 3)

    async def test_constraints_resource(self):
        import json
        self.assertIn("stitch://constraints", json.loads(api.constraints())["resource"])

    async def test_validation_before_network(self):
        cases = [(api.stitch_resolve, {"proteins": []}),
                 (api.stitch_resolve, {"proteins": ["TP53"] * 101}),
                 (api.stitch_resolve, {"proteins": ["TP53,MDM2"]}),
                 (api.stitch_resolve, {"proteins": ["TP53"], "species": 0}),
                 (api.stitch_interactions, {"proteins": ["TP53"], "required_score": 1001}),
                 (api.stitch_interactions, {"proteins": ["TP53"], "limit": 1001}),
                 (api.stitch_interactions, {"proteins": ["a" * 101]}),
                 (api.stitch_enrichment, {"proteins": []})]
        for func, kwargs in cases:
            with self.subTest(tool=func.__name__, kwargs=kwargs), self.assertRaises(ValueError):
                await func(**kwargs)

    async def test_api_error(self):
        with self.mock_http(lambda req: httpx.Response(500)):
            with self.assertRaises(httpx.HTTPStatusError):
                await api.stitch_interactions(["TP53"])
