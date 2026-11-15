import json
from unittest import mock

import httpx

from servers.ensembl_mcp import api
from tests.helpers import HTTPTestCase


class PlantTests(HTTPTestCase):
    async def test_species_assembly(self):
        with self.mock_http(lambda req: httpx.Response(200, json={"species": [{"common_name": "rice", "assembly": "IRGSP-1.0"}]})):
            self.assertEqual((await api.ensembl_species())["species"][0]["assembly"], "IRGSP-1.0")

    async def test_symbol_lookup(self):
        def handler(req):
            self.assertTrue(req.url.path.endswith("/lookup/symbol/arabidopsis_thaliana/PHYB"))
            return httpx.Response(200, json={"id": "AT2G18790", "display_name": "PHYB", "source": "araport11"})
        with self.mock_http(handler):
            result = await api.ensembl_lookup_symbol("PHYB", species="arabidopsis_thaliana")
            self.assertEqual(result["gene"]["id"], "AT2G18790")
            self.assertEqual(result["species"], "arabidopsis_thaliana")
        with self.assertRaises(ValueError):
            await api.ensembl_lookup_symbol("bad symbol!")

    async def test_division_species_truncation(self):
        def handler(req):
            self.assertEqual(req.url.params["division"], "EnsemblFungi")
            return httpx.Response(200, json={"species": [{"display_name": f"fungus {i}"} for i in range(5)]})
        with self.mock_http(handler):
            result = await api.ensembl_species("fungus", division="EnsemblFungi", limit=3)
            self.assertEqual(len(result["species"]), 3)
            self.assertEqual(result["total"], 5)
            self.assertTrue(result["truncated"])

    async def test_homologs_compara_choices(self):
        def handler(req):
            self.assertEqual(req.url.params["compara"], "fungi")
            return httpx.Response(200, json={"data": [{"homologies": [{"type": "ortholog_one2one"}]}]})
        with self.mock_http(handler):
            result = await api.ensembl_homologs("YAL060W", species="saccharomyces_cerevisiae", compara="fungi")
            self.assertEqual(result["homologies"][0]["type"], "ortholog_one2one")
        for bad in ("bacteria", "vert"):
            with self.subTest(compara=bad), self.assertRaises(ValueError):
                await api.ensembl_homologs("YAL060W", compara=bad)

    async def test_batch_preserves_unmapped_ids(self):
        def handler(req):
            self.assertEqual(req.url.params["species"], "oryza_sativa")
            self.assertEqual(json.loads(req.content)["ids"], ["Os01g0100100", "missing"])
            return httpx.Response(200, json={"Os01g0100100": {"assembly_name": "IRGSP-1.0"}, "missing": None})
        with self.mock_http(handler):
            self.assertIsNone((await api.ensembl_lookup_batch(["Os01g0100100", "missing"]))["records"]["missing"])

    async def test_sequence_limit(self):
        with self.mock_http(lambda req: httpx.Response(200, json={"seq": "ACGT", "id": "Os01g0100100"})):
            self.assertEqual((await api.ensembl_sequence("Os01g0100100"))["sequences"][0]["seq"], "ACGT")
            with self.assertRaises(ValueError):
                await api.ensembl_sequence("Os01g0100100", max_length=2)

    async def test_plant_compara_and_limit(self):
        def handler(req):
            self.assertEqual(req.url.params["compara"], "plants")
            self.assertEqual(req.url.params["sequence"], "none")
            return httpx.Response(200, json={"data": [{"homologies": [{"type": "ortholog_one2one"}] * 3}]})
        with self.mock_http(handler):
            result = await api.ensembl_homologs("Os01g0100100", limit=1)
            self.assertTrue(result["truncated"])
            self.assertEqual(len(result["homologies"]), 1)

    async def test_all_tool_validation(self):
        for func, args in [(api.ensembl_species, {"query": ""}), (api.ensembl_lookup_batch, {"ids": []}),
                           (api.ensembl_sequence, {"identifier": "x", "sequence_type": "bad"}),
                           (api.ensembl_homologs, {"identifier": "x", "homology_type": "bad"})]:
            with self.subTest(tool=func.__name__), self.assertRaises(ValueError):
                await func(**args)

    async def test_variation_lookup(self):
        def handler(req):
            self.assertTrue(req.url.path.endswith("/variation/oryza_sativa/vcZ240K4H"))
            return httpx.Response(200, json={"name": "vcZ240K4H", "most_severe_consequence": "intergenic_variant"})
        with self.mock_http(handler):
            result = await api.ensembl_variation("oryza_sativa", "vcZ240K4H")
            self.assertEqual(result["variant"]["name"], "vcZ240K4H")
            self.assertEqual(result["species"], "oryza_sativa")
        with self.assertRaises(httpx.HTTPStatusError):
            with self.mock_http(lambda req: httpx.Response(400, json={"error": "rs1006 not found for oryza_sativa"})):
                await api.ensembl_variation("oryza_sativa", "rs1006")
        with self.assertRaises(httpx.HTTPStatusError):
            with self.mock_http(lambda req: httpx.Response(404)):
                await api.ensembl_variation("oryza_sativa", "vcMISSING")

    async def test_variation_validation_no_network(self):
        with mock.patch("servers.ensembl_mcp.api.request", side_effect=AssertionError("network call")):
            for func, args in [(api.ensembl_variation, {"species": "bad species!", "variant_id": "rs699"}),
                               (api.ensembl_variation, {"species": "oryza_sativa", "variant_id": "bad id!"}),
                               (api.ensembl_region_variants, {"species": "oryza_sativa", "region": "no-colon-here"}),
                               (api.ensembl_region_variants, {"species": "oryza_sativa", "region": "1:1-100", "limit": 0}),
                               (api.ensembl_region_variants, {"species": "oryza_sativa", "region": "1:1-100", "limit": 201}),
                               (api.ensembl_region_variants, {"species": "oryza_sativa", "region": "1:1-100", "offset": -1}),
                               (api.ensembl_region_variants, {"species": "oryza_sativa", "region": "1:1-100", "offset": 10001})]:
                with self.subTest(tool=func.__name__, args=args), self.assertRaises(ValueError):
                    await func(**args)

    async def test_region_variants_pagination(self):
        def handler(req):
            self.assertIn("/overlap/region/arabidopsis_thaliana/1:3631-4000", req.url.path)
            self.assertEqual(req.url.params["feature"], "variation")
            return httpx.Response(200, json=[{"id": f"v{i}", "start": 3631 + i} for i in range(5)])
        with self.mock_http(handler):
            page1 = await api.ensembl_region_variants("arabidopsis_thaliana", "1:3631-4000", limit=2)
            self.assertEqual([v["id"] for v in page1["variants"]], ["v0", "v1"])
            self.assertEqual(page1["total"], 5)
            self.assertTrue(page1["truncated"])
            page2 = await api.ensembl_region_variants("arabidopsis_thaliana", "1:3631-4000", limit=2, offset=4)
            self.assertEqual([v["id"] for v in page2["variants"]], ["v4"])
            self.assertFalse(page2["truncated"])

    async def test_api_failure(self):
        with self.mock_http(lambda req: httpx.Response(500)):
            with self.assertRaises(httpx.HTTPStatusError):
                await api.ensembl_species()
