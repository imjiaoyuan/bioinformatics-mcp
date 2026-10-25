import json

import httpx

from servers.ensembl_mcp import server
from tests.helpers import HTTPTestCase


class PlantTests(HTTPTestCase):
    async def test_species_assembly(self):
        with self.mock_http(lambda req: httpx.Response(200, json={"species": [{"common_name": "rice", "assembly": "IRGSP-1.0"}]})):
            self.assertEqual((await server.ensembl_species())["species"][0]["assembly"], "IRGSP-1.0")

    async def test_batch_preserves_unmapped_ids(self):
        def handler(req):
            self.assertEqual(req.url.params["species"], "oryza_sativa")
            self.assertEqual(json.loads(req.content)["ids"], ["Os01g0100100", "missing"])
            return httpx.Response(200, json={"Os01g0100100": {"assembly_name": "IRGSP-1.0"}, "missing": None})
        with self.mock_http(handler):
            self.assertIsNone((await server.ensembl_lookup_batch(["Os01g0100100", "missing"]))["records"]["missing"])

    async def test_sequence_limit(self):
        with self.mock_http(lambda req: httpx.Response(200, json={"seq": "ACGT", "id": "Os01g0100100"})):
            self.assertEqual((await server.ensembl_sequence("Os01g0100100"))["sequences"][0]["seq"], "ACGT")
            with self.assertRaises(ValueError):
                await server.ensembl_sequence("Os01g0100100", max_length=2)

    async def test_plant_compara_and_limit(self):
        def handler(req):
            self.assertEqual(req.url.params["compara"], "plants")
            self.assertEqual(req.url.params["sequence"], "none")
            return httpx.Response(200, json={"data": [{"homologies": [{"type": "ortholog_one2one"}] * 3}]})
        with self.mock_http(handler):
            result = await server.ensembl_homologs("Os01g0100100", limit=1)
            self.assertTrue(result["truncated"])
            self.assertEqual(len(result["homologies"]), 1)

    async def test_all_tool_validation(self):
        for func, args in [(server.ensembl_species, {"query": ""}), (server.ensembl_lookup_batch, {"ids": []}),
                           (server.ensembl_sequence, {"identifier": "x", "sequence_type": "bad"}),
                           (server.ensembl_homologs, {"identifier": "x", "homology_type": "bad"})]:
            with self.subTest(tool=func.__name__), self.assertRaises(ValueError):
                await func(**args)

    async def test_api_failure(self):
        with self.mock_http(lambda req: httpx.Response(500)):
            with self.assertRaises(httpx.HTTPStatusError):
                await server.ensembl_species()
