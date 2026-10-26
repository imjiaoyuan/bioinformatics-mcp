import json
from unittest.mock import AsyncMock, patch

import httpx

from servers.cbioportal_mcp import server
from tests.helpers import HTTPTestCase


class CBioPortalTests(HTTPTestCase):
    async def test_studies_samples_clinical_profiles(self):
        requests = []
        def handler(req):
            requests.append(req)
            self.assertEqual(req.url.params["pageSize"], "1")
            return httpx.Response(200, headers={"total-count": "3"}, json=[{"sampleId": "sample", "patientId": "patient"}])
        with self.mock_http(handler), patch("common.http.asyncio.sleep", new_callable=AsyncMock):
            for call in [server.cbioportal_studies("breast", limit=1), server.cbioportal_samples("brca_tcga", limit=1),
                         server.cbioportal_clinical("brca_tcga", "OS_MONTHS", "PATIENT", limit=1),
                         server.cbioportal_molecular_profiles("brca_tcga", limit=1)]:
                result = await call
                self.assertTrue(result["has_more"])
                self.assertEqual(result["total"], 3)
        self.assertEqual(requests[0].url.params["keyword"], "breast")
        self.assertEqual(requests[2].url.params["clinicalDataType"], "PATIENT")
        self.assertEqual(requests[2].url.params["attributeId"], "OS_MONTHS")

    async def test_measurements_preserve_profile_and_sample_gene_pairs(self):
        requests = []
        def handler(req):
            requests.append(req)
            if req.method == "GET":
                return httpx.Response(200, json={"molecularAlterationType": "MRNA_EXPRESSION", "datatype": "Z-SCORE", "studyId": "brca_tcga"})
            self.assertEqual(json.loads(req.content), {"sampleIds": ["S1"], "entrezGeneIds": [7157]})
            return httpx.Response(200, json=[{"sampleId": "S1", "entrezGeneId": 7157, "value": -1.3}])
        with self.mock_http(handler), patch("common.http.asyncio.sleep", new_callable=AsyncMock):
            result = await server.cbioportal_molecular_data("brca_zscores", ["S1", "S1"], [7157])
        self.assertEqual(result["profile"]["datatype"], "Z-SCORE")
        self.assertEqual(result["results"][0]["value"], -1.3)
        self.assertEqual(result["requested_pairs"], 1)
        self.assertNotIn("pageSize", requests[-1].url.params)

    async def test_mutations_and_wrong_profile(self):
        def handler(req):
            if req.method == "GET":
                return httpx.Response(200, json={"molecularAlterationType": "MUTATION_EXTENDED"})
            self.assertEqual(req.url.params["pageNumber"], "2")
            return httpx.Response(200, json=[{"proteinChange": "R175H", "ncbiBuild": "GRCh37"}])
        with self.mock_http(handler), patch("common.http.asyncio.sleep", new_callable=AsyncMock):
            result = await server.cbioportal_mutations("brca_mutations", ["S1"], [7157], limit=1, page=2)
            self.assertEqual(result["results"][0]["ncbiBuild"], "GRCh37")
            self.assertIsNone(result["has_more"])
            self.assertTrue(result["may_have_more"])
            with self.assertRaises(ValueError):
                await server.cbioportal_molecular_data("brca_mutations", ["S1"], [7157])

    async def test_validation_all_tools_and_product_bound(self):
        for func, args in [(server.cbioportal_studies, {"limit": 0}), (server.cbioportal_samples, {"study_id": "../"}),
                           (server.cbioportal_clinical, {"study_id": "brca", "level": "wrong"}),
                           (server.cbioportal_molecular_profiles, {"study_id": "brca", "page": -1}),
                           (server.cbioportal_mutations, {"profile_id": "p", "sample_ids": [], "gene_ids": [1]}),
                           (server.cbioportal_molecular_data, {"profile_id": "p", "sample_ids": ["s"], "gene_ids": [True]}),
                           (server.cbioportal_molecular_data, {"profile_id": "p", "sample_ids": [f"s{i}" for i in range(100)], "gene_ids": list(range(1, 12))})]:
            with self.subTest(tool=func.__name__), self.assertRaises(ValueError):
                await func(**args)

    async def test_empty_and_api_error(self):
        with self.mock_http(lambda req: httpx.Response(200, headers={"total-count": "0"}, json=[])):
            result = await server.cbioportal_studies()
            self.assertEqual(result["results"], [])
            self.assertFalse(result["has_more"])
        with self.mock_http(lambda req: httpx.Response(404)):
            with self.assertRaises(httpx.HTTPStatusError):
                await server.cbioportal_samples("missing")
