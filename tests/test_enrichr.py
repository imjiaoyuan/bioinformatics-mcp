"""Mocked tests for the Enrichr MCP api."""
import httpx

from servers.enrichr_mcp import api
from tests.helpers import HTTPTestCase

STATISTICS = {"statistics": [
    {"libraryName": "ChEA_2022", "numTerms": 1622, "genesPerTerm": 37,
     "geneCoverage": 13362, "link": "https://maayanlab.cloud/chea"},
    {"libraryName": "GO_Biological_Process_2023", "numTerms": 7447,
     "genesPerTerm": 189, "geneCoverage": 6483, "link": "http://geneontology.org/"}],
    "categories": []}
ENRICH = {"ChEA_2022": [
    {"rank": 1, "term": "TP53 Regulates Genes", "p-value": 0.0012, "z-score": 2.31,
     "combined-score": 7.44, "overlapping-genes": ["TP53"], "adj. p-value": 0.05},
    {"rank": 2, "term": "BRCA1 Regulates Genes", "p-value": 0.02, "z-score": -1.2,
     "combined-score": 3.1, "overlapping-genes": ["BRCA1", "EGFR"], "adj. p-value": 0.4}]}
SUBMIT = {"shortId": "133c5f01311b133553b96b77289727a5", "userListId": 142351519}


class EnrichrTests(HTTPTestCase):
    async def test_libraries_submit_and_enrich(self):
        seen = []

        def handler(req):
            seen.append((req.url.path, req.method))
            if req.url.path.endswith("/datasetStatistics"):
                return httpx.Response(200, json=STATISTICS)
            if req.url.path.endswith("/addList"):
                body = req.read().decode()
                self.assertIn("TP53", body)
                self.assertIn("BRCA1", body)
                self.assertIn("multipart", req.headers["content-type"])
                return httpx.Response(200, json=SUBMIT)
            if req.url.path.endswith("/enrich"):
                self.assertEqual(req.url.params["userListId"], "142351519")
                self.assertEqual(req.url.params["backgroundType"], "ChEA_2022")
                return httpx.Response(200, json=ENRICH)
            raise AssertionError(f"unexpected path: {req.url.path}")

        with self.mock_http(handler):
            libraries = await api.enrichr_libraries(limit=1)
            self.assertEqual(libraries["results"][0]["library_name"], "ChEA_2022")
            self.assertEqual(libraries["total"], 2)
            self.assertTrue(libraries["truncated"])
            submitted = await api.enrichr_submit_genes(["tp53", "BRCA1", "EGFR"], description="probe")
            self.assertEqual(submitted["user_list_id"], 142351519)
            self.assertEqual(submitted["genes"], ["TP53", "BRCA1", "EGFR"])
            self.assertEqual(submitted["gene_count"], 3)
            enrich = await api.enrichr_enrich("142351519", "ChEA_2022", limit=1)
            self.assertEqual(enrich["results"][0]["term"], "TP53 Regulates Genes")
            self.assertEqual(enrich["results"][0]["p_value"], 0.0012)
            self.assertEqual(enrich["results"][0]["overlapping_genes"], ["TP53"])
            self.assertEqual(enrich["library"], "ChEA_2022")
        self.assertEqual(seen[-1][1], "GET")

    async def test_missing_library_results_are_an_error(self):
        with self.mock_http(lambda req: httpx.Response(200, json={"other_library": []})):
            with self.assertRaises(ValueError):
                await api.enrichr_enrich("142351519", "ChEA_2022")

    async def test_unexpected_submit_payload_is_an_error(self):
        with self.mock_http(lambda req: httpx.Response(200, json={"expired": True})):
            with self.assertRaises(ValueError):
                await api.enrichr_submit_genes(["TP53"])

    async def test_validation_before_network(self):
        cases = [(api.enrichr_libraries, {"limit": 0}),
                 (api.enrichr_libraries, {"offset": -1}),
                 (api.enrichr_submit_genes, {"genes": []}),
                 (api.enrichr_submit_genes, {"genes": ["TP53;drop"]}),
                 (api.enrichr_submit_genes, {"genes": ["TP53"] * 1001}),
                 (api.enrichr_submit_genes, {"genes": ["TP53"], "description": "d\nx"}),
                 (api.enrichr_enrich, {"user_list_id": "bad", "library": "ChEA_2022"}),
                 (api.enrichr_enrich, {"user_list_id": "142351519", "library": "ChEA/2022"}),
                 (api.enrichr_enrich, {"user_list_id": "142351519", "library": "ChEA_2022", "limit": 0})]
        for func, kwargs in cases:
            with self.subTest(tool=func.__name__, kwargs=kwargs), self.assertRaises(ValueError):
                await func(**kwargs)

    async def test_api_error(self):
        with self.mock_http(lambda req: httpx.Response(503)):
            with self.assertRaises(httpx.HTTPStatusError):
                await api.enrichr_libraries()
