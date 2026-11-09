from unittest.mock import AsyncMock, patch

import httpx

from servers.gtex_mcp import server
from tests.helpers import HTTPTestCase


class GtexTests(HTTPTestCase):
    async def test_all_tools_success(self):
        paths = []
        def handler(req):
            paths.append((req.url.path, dict(req.url.params)))
            if req.url.path.endswith("/api/v2/"):
                return httpx.Response(200, json={"service": "GTEx Portal API", "version": "2.0.0"})
            if "tissueSiteDetail" in req.url.path:
                self.assertEqual(req.url.params["itemsPerPage"], "10")
                self.assertEqual(req.url.params["page"], "1")
                return httpx.Response(200, json={"data": [{"tissueSiteDetailId": "Brain_Cerebellum",
                                                           "tissueSiteDetail": "Brain - Cerebellum",
                                                           "ontologyId": "UBERON:0002037"}],
                                                 "paging_info": {"totalNumberOfItems": 54, "page": 1}})
            if "reference/gene" in req.url.path:
                self.assertEqual(req.url.params["geneId"], "ACTN2")
                return httpx.Response(200, json={"data": [{"geneSymbol": "ACTN2",
                                                           "gencodeId": "ENSG00000077522.12",
                                                           "chromosome": "chr1",
                                                           "start": 236686454, "end": 236764631,
                                                           "genomeBuild": "GRCh38/hg38"}],
                                                 "paging_info": {"totalNumberOfItems": 1}})
            if "medianGeneExpression" in req.url.path:
                self.assertEqual(req.url.params["gencodeId"], "ENSG00000077522.12")
                self.assertEqual(req.url.params["datasetId"], "gtex_v10")
                return httpx.Response(200, json={"data": [{"gencodeId": "ENSG00000077522.12",
                                                           "tissueSiteDetailId": "Brain_Cerebellum",
                                                           "median": 4093.4, "unit": "TPM"}],
                                                 "paging_info": {"totalNumberOfItems": 54}})
            if "geneExpression" in req.url.path:
                self.assertEqual(req.url.params["tissueSiteDetailId"], "Brain_Cerebellum")
                self.assertEqual(req.url.params["datasetId"], "gtex_v11")
                return httpx.Response(200, json={"data": [{"gencodeId": "ENSG00000077522.12",
                                                           "sampleId": "GTEX-1117F",
                                                           "value": 4319.8, "unit": "TPM"}],
                                                 "paging_info": {"totalNumberOfItems": 24}})
            self.assertIn("singleTissueEqtl", req.url.path)
            self.assertEqual(req.url.params["variantId"], "chr1_236686454_G_A_b38")
            return httpx.Response(200, json={"data": [{"snpId": "rs2854464",
                                                       "gencodeId": "ENSG00000077522.12",
                                                       "tissueSiteDetailId": "Brain_Cerebellum",
                                                       "pValue": 1.2e-40, "nes": -0.61,
                                                       "qValue": 0.0}],
                                           "paging_info": {"totalNumberOfItems": 1}})
        with self.mock_http(handler), patch("common.http.asyncio.sleep", new_callable=AsyncMock):
            self.assertEqual((await server.gtex_service_info())["version"], "2.0.0")
            tissue = (await server.gtex_tissue_list(limit=10, page=1))["data"][0]
            self.assertEqual(tissue["ontologyId"], "UBERON:0002037")
            gene = (await server.gtex_gene_search("ACTN2"))["data"][0]
            self.assertEqual(gene["gencodeId"], "ENSG00000077522.12")
            self.assertEqual(gene["genomeBuild"], "GRCh38/hg38")
            median = (await server.gtex_median_gene_expression("ENSG00000077522.12"))["data"][0]
            self.assertEqual(median["unit"], "TPM")
            per_sample = (await server.gtex_gene_expression("ENSG00000077522.12", "Brain_Cerebellum",
                                                            dataset_id="gtex_v11"))["data"][0]
            self.assertEqual(per_sample["sampleId"], "GTEX-1117F")
            eqtl = (await server.gtex_eqtl(gencode_id="ENSG00000077522.12",
                                           variant_id="chr1_236686454_G_A_b38"))["data"][0]
            self.assertLess(eqtl["pValue"], 0.05)
        self.assertIn("dataset/tissueSiteDetail", paths[1][0])

    async def test_validation_all_tools(self):
        cases = [(server.gtex_tissue_list, {"limit": 0}), (server.gtex_tissue_list, {"page": -1}),
                 (server.gtex_gene_search, {"gene": "  "}),
                 (server.gtex_median_gene_expression, {"gencode_id": "ACTN2; drop"}),
                 (server.gtex_median_gene_expression, {"gencode_id": "ENSG00000077522.12", "dataset_id": "v9"}),
                 (server.gtex_median_gene_expression, {"gencode_id": "ENSG00000077522.12", "tissue_id": "brain!"}),
                 (server.gtex_gene_expression, {"gencode_id": "ENSG00000077522.12", "tissue_id": "bad tissue"}),
                 (server.gtex_gene_expression, {"gencode_id": "ENSG00000077522.12", "tissue_id": "Brain_Cerebellum",
                                                "dataset_id": "gtex_v7"}),
                 (server.gtex_eqtl, {}), (server.gtex_eqtl, {"tissue_id": "", "gencode_id": "x"}),
                 (server.gtex_eqtl, {"gencode_id": "ENSG00000077522.12", "limit": 101})]
        for func, args in cases:
            with self.subTest(tool=func.__name__, args=args), self.assertRaises(ValueError):
                await func(**args)

    async def test_api_error(self):
        with self.mock_http(lambda req: httpx.Response(404)):
            with self.assertRaises(httpx.HTTPStatusError):
                await server.gtex_median_gene_expression("ENSG99999999999.1")
