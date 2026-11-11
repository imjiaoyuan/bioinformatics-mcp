import os
from unittest.mock import AsyncMock, patch

import httpx

from servers.disgenet_mcp import api
from tests.helpers import HTTPTestCase

KEY = {"DISGENET_API_KEY": "test-key"}


class DisGeNETTests(HTTPTestCase):
    async def test_summaries_and_associations(self):
        paths, params = [], {}

        def handler(req):
            paths.append(req.url.path)
            params.update(req.url.params)
            if req.url.path.endswith("gda/summary"):
                return httpx.Response(200, json={"parameters": {"sourc": "ALL"}, "sources": [
                    {"source": "CURATED", "gdas": 50000, "genes": 5000, "diseases": 8000}]})
            if req.url.path.endswith("gda/gene"):
                return httpx.Response(200, json={"parameters": {"gene_ncbi_id": "351"}, "results": [
                    {"gene_symbol": "APP", "diseaseid": "C0002366", "score": 0.3}]})
            if req.url.path.endswith("gda/disease"):
                return httpx.Response(200, json={"parameters": {"diseaseid": "C0002394"}, "results": [
                    {"gene_ncbi_id": "351", "gene_symbol": "APP", "score": 0.9}]})
            if req.url.path.endswith("vda/summary"):
                return httpx.Response(200, json={"parameters": {"sourc": "ALL"}, "sources": [
                    {"source": "BEFREE", "vdas": 20000, "variants": 10000, "diseases": 4000}]})
            if req.url.path.endswith("vda/variant"):
                return httpx.Response(200, json={"parameters": {"snp_id": "rs11575418"}, "results": [
                    {"snp_id": "rs11575418", "diseaseid": "C0038356", "score": 0.1}]})
            return httpx.Response(200, json={"parameters": {"diseaseid": "C0038356"}, "results": [
                {"vdb_id": "571309", "snp_id": "rs11575418", "score": 0.1}]})

        with self.mock_http(handler), patch("common.http.asyncio.sleep", new_callable=AsyncMock), \
                patch.dict(os.environ, KEY):
            summary = await api.disgenet_gda_summary()
            self.assertEqual(summary["sources"][0]["gdas"], 50000)
            self.assertIn("sourc=ALL", summary["source_url"])
            gda = (await api.disgenet_gene_diseases(ncbi_gene_id="351"))["results"][0]
            self.assertEqual(gda["gene_symbol"], "APP")
            self.assertGreater(gda["score"], 0)
            self.assertEqual((await api.disgenet_disease_genes("c0002394"))["parameters"]["diseaseid"],
                             "C0002394")
            vsummary = await api.disgenet_vda_summary("curated")
            self.assertEqual(params["sourc"], "CURATED")
            self.assertEqual(vsummary["sources"][0]["vdas"], 20000)
            vda = (await api.disgenet_variant_diseases(snp_id="RS11575418"))["results"][0]
            self.assertEqual(vda["diseaseid"], "C0038356")
            self.assertEqual((await api.disgenet_disease_variants("C0038356"))["results"][0]["vdb_id"],
                             "571309")
        self.assertIn("gda/summary", paths[-6])
        for fragment in ["gda/gene", "gda/disease", "vda/summary", "vda/variant", "vda/disease"]:
            self.assertTrue(any(p.endswith(fragment) for p in paths), fragment)
        self.assertEqual(params["Authorization"] if "Authorization" in params else "not-in-params",
                         "not-in-params")

    async def test_pagination_maps_to_page_number(self):
        def handler(req):
            self.assertEqual(req.url.params["page_number"], "1")
            return httpx.Response(200, json={"results": []})

        with self.mock_http(handler), patch("common.http.asyncio.sleep", new_callable=AsyncMock), \
                patch.dict(os.environ, KEY):
            result = await api.disgenet_gene_diseases(gene_symbol="APP", limit=10, offset=10)
        self.assertEqual(result["results"], [])
        self.assertIn("source_url", result)

    async def test_missing_api_key(self):
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaises(ValueError):
                await api.disgenet_gda_summary()

    async def test_validation_all_tools(self):
        for func, args in [(api.disgenet_gda_summary, {"sourc": "bad"}),
                           (api.disgenet_gene_diseases, {}),
                           (api.disgenet_gene_diseases, {"ncbi_gene_id": "abc"}),
                           (api.disgenet_gene_diseases, {"gene_symbol": "../"}),
                           (api.disgenet_disease_genes, {"disease_cui": "disease"}),
                           (api.disgenet_disease_genes, {"disease_cui": "C1", "limit": 101}),
                           (api.disgenet_vda_summary, {"sourc": "bad"}),
                           (api.disgenet_variant_diseases, {}),
                           (api.disgenet_variant_diseases, {"snp_id": "11575418"}),
                           (api.disgenet_variant_diseases, {"vdb_id": "x"}),
                           (api.disgenet_disease_variants, {"disease_cui": ""})]:
            with self.subTest(tool=func.__name__), patch.dict(os.environ, KEY), \
                    self.assertRaises(ValueError):
                await func(**args)

    async def test_api_error(self):
        with self.mock_http(lambda req: httpx.Response(404)):
            with patch.dict(os.environ, KEY), self.assertRaises(httpx.HTTPStatusError):
                await api.disgenet_gene_diseases(ncbi_gene_id="351")
