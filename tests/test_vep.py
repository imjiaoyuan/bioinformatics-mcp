from unittest.mock import AsyncMock, patch

import httpx

from servers.vep_mcp import server
from tests.helpers import HTTPTestCase

HGVS = "ENST00000366667:c.803C>T"
RESPONSE = [{"input": "9:g.22125504G>C", "id": "9:g.22125504G>C",
             "most_severe_consequence": "missense_variant",
             "transcript_consequences": [{"transcript_id": "ENST00000366667",
                                          "variant_allele": "C",
                                          "consequence_terms": ["missense_variant"]}]}]


class VEPTests(HTTPTestCase):
    async def test_all_tools_success(self):
        def handler(req):
            paths.append((req.method, req.url.path, dict(req.url.params)))
            if req.method == "GET":
                return httpx.Response(200, json=RESPONSE)
            body = req.read().decode()
            self.assertIn("application/json", req.headers.get("content-type", ""))
            if req.url.path.endswith("/hgvs"):
                self.assertIn("hgvs_notations", body)
            elif req.url.path.endswith("/region"):
                self.assertIn("variants", body)
            else:
                self.assertIn("ids", body)
            return httpx.Response(200, json=RESPONSE)
        paths = []
        flags = {"pick": True, "canonical": True, "hgvs_labels": True, "protein": True,
                 "mane": True, "refseq": True, "numbers": True, "variant_class": True,
                 "merged": True, "distance": 5000}
        with self.mock_http(handler), patch("common.http.asyncio.sleep", new_callable=AsyncMock):
            single = await server.vep_hgvs("human", HGVS, **flags)
            self.assertIn("/vep/human/hgvs/ENST00000366667:c.803C%3ET", single["source_url"])
            self.assertEqual(single["results"][0]["most_severe_consequence"], "missense_variant")
            for tool, values in [(server.vep_hgvs_batch, {"hgvs_notations": [HGVS]}),
                                 (server.vep_region, {"region": "9:22125504-22125504:G/C"}),
                                 (server.vep_region_batch, {"variants": ["9 22125504 rs1 G C . . ."]}),
                                 (server.vep_id, {"variant_id": "rs56116432"}),
                                 (server.vep_id_batch, {"variant_ids": ["rs56116432", "COSM476"]})]:
                result = await tool("homo_sapiens", **values, **flags)
                self.assertIn("source_url", result)
                self.assertEqual(result["results"][0]["input"], "9:g.22125504G>C")
        for path in ["/vep/human/hgvs/ENST00000366667:c.803C>T", "/vep/homo_sapiens/hgvs",
                     "/vep/homo_sapiens/region/9:22125504-22125504:G/C", "/vep/homo_sapiens/region",
                     "/vep/homo_sapiens/id/rs56116432", "/vep/homo_sapiens/id"]:
            self.assertIn(path, [p[1] for p in paths])
        self.assertEqual(paths[0][2]["pick"], "1")
        self.assertEqual(paths[0][2]["distance"], "5000")
        self.assertEqual(paths[0][2]["content-type"], "application/json")
        self.assertTrue(all(p[2]["content-type"] == "application/json" for p in paths))

    async def test_default_flags_omit_optional_params(self):
        def handler(req):
            self.assertNotIn("pick", req.url.params)
            self.assertNotIn("distance", req.url.params)
            return httpx.Response(200, json=RESPONSE)
        with self.mock_http(handler), patch("common.http.asyncio.sleep", new_callable=AsyncMock):
            await server.vep_hgvs("human", HGVS)

    async def test_validation_all_tools(self):
        bad_flags = {"distance": 25001}
        for func, kwargs in [(server.vep_hgvs, {"species": "human", "hgvs": "not-hgvs"}),
                             (server.vep_hgvs, {"species": "human", "hgvs": HGVS, **bad_flags}),
                             (server.vep_hgvs, {"species": "hu man", "hgvs": HGVS}),
                             (server.vep_hgvs_batch, {"species": "human", "hgvs_notations": []}),
                             (server.vep_hgvs_batch, {"species": "human",
                                                      "hgvs_notations": ["x" for _ in range(201)]}),
                             (server.vep_hgvs_batch, {"species": "human", "hgvs_notations": [HGVS, "bad hgvs"]}),
                             (server.vep_region, {"species": "human", "region": "9:abc-2:G/C"}),
                             (server.vep_region, {"species": "human", "region": "9:100"}),
                             (server.vep_region_batch, {"species": "human", "variants": ["9 100 rs1 G"]}),
                             (server.vep_id, {"species": "human", "variant_id": "1rs56116432"}),
                             (server.vep_id, {"species": "human", "variant_id": "rs 56116432"}),
                             (server.vep_id_batch, {"species": "human", "variant_ids": []}),
                             (server.vep_id_batch, {"species": "human",
                                                    "variant_ids": ["rs1" for _ in range(201)]})]:
            with self.subTest(tool=func.__name__, kwargs=kwargs), self.assertRaises(ValueError):
                await func(**kwargs)

    async def test_api_error(self):
        with self.mock_http(lambda req: httpx.Response(404)):
            with self.assertRaises(httpx.HTTPStatusError):
                await server.vep_hgvs("human", HGVS)
