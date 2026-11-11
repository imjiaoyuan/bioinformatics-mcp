from unittest.mock import AsyncMock, patch

import httpx

from servers.alphafold_mcp import api
from tests.helpers import HTTPTestCase


def _entry(entry_id="AF-P00533-F1", accession="P00533"):
    return {
        "entryId": entry_id,
        "uniprotAccession": accession,
        "gene": "EGFR",
        "organismScientificName": "Homo sapiens",
        "sequenceChecksum": "99d03b567dbcdd7fb0dd21fb40d5d283",
        "latestVersion": 6,
        "globalMetricValue": 75.94,
        "fractionPlddtVeryLow": 0.228,
        "fractionPlddtLow": 0.065,
        "fractionPlddtConfident": 0.233,
        "fractionPlddtVeryHigh": 0.474,
        "pdbUrl": f"https://alphafold.ebi.ac.uk/files/{entry_id}-model_v6.pdb",
        "cifUrl": f"https://alphafold.ebi.ac.uk/files/{entry_id}-model_v6.cif",
        "bcifUrl": f"https://alphafold.ebi.ac.uk/files/{entry_id}-model_v6.bcif",
        "paeImageUrl": f"https://alphafold.ebi.ac.uk/files/{entry_id}-predicted_aligned_error_v6.png",
        "msaUrl": f"https://alphafold.ebi.ac.uk/files/msa/{entry_id}-msa_v6.a3m",
        "plddtDocUrl": f"https://alphafold.ebi.ac.uk/files/{entry_id}-confidence_v6.json",
        "paeDocUrl": f"https://alphafold.ebi.ac.uk/files/{entry_id}-predicted_aligned_error_v6.json",
    }


class AlphaFoldTests(HTTPTestCase):
    async def test_prediction_confidence_and_urls(self):
        def handler(req):
            self.assertEqual(req.url.host, "alphafold.ebi.ac.uk")
            self.assertEqual(req.url.path, "/api/prediction/P00533")
            return httpx.Response(200, json=[_entry()])
        with self.mock_http(handler), patch("common.http.asyncio.sleep", new_callable=AsyncMock):
            prediction = await api.alphafold_prediction("p00533")
            self.assertEqual(prediction["results"][0]["entryId"], "AF-P00533-F1")
            self.assertEqual(prediction["results"][0]["source_url"],
                             "https://alphafold.ebi.ac.uk/api/prediction/P00533")
            confidence = (await api.alphafold_confidence("P00533"))["results"][0]
            self.assertEqual(confidence["global_metric_value"], 75.94)
            self.assertEqual(confidence["fraction_plddt_very_high"], 0.474)
            self.assertTrue(confidence["pae_doc_url"].endswith("-predicted_aligned_error_v6.json"))
            urls = (await api.alphafold_model_urls("P00533"))["results"][0]
            self.assertEqual(urls["pdb_url"], "https://alphafold.ebi.ac.uk/files/AF-P00533-F1-model_v6.pdb")
            self.assertEqual(urls["cif_url"], "https://alphafold.ebi.ac.uk/files/AF-P00533-F1-model_v6.cif")

    async def test_batch_lookup_with_missing(self):
        def handler(req):
            if req.url.path.endswith("/P99999"):
                return httpx.Response(404)
            return httpx.Response(200, json=[_entry(accession=req.url.path.rsplit("/", 1)[1])])
        with self.mock_http(handler), patch("common.http.asyncio.sleep", new_callable=AsyncMock):
            result = await api.alphafold_batch(["P00533", "p99999"], limit=1)
            self.assertEqual(result["pagination"], "local")
            self.assertEqual(result["total"], 1)
            self.assertEqual(result["results"][0]["uniprotAccession"], "P00533")
            self.assertEqual(result["missing"], ["P99999"])
            self.assertFalse(result["truncated"])

    async def test_validation_all_tools(self):
        for func, args in [(api.alphafold_prediction, {"uniprot": "bad"}),
                           (api.alphafold_batch, {"accessions": []}),
                           (api.alphafold_batch, {"accessions": ["P00533"] * 51}),
                           (api.alphafold_batch, {"accessions": ["P00533"], "limit": 101}),
                           (api.alphafold_confidence, {"uniprot": "1P005"}),
                           (api.alphafold_model_urls, {"uniprot": ""})]:
            with self.subTest(tool=func.__name__), \
                    self.mock_http(lambda req: httpx.Response(200, json=[])), \
                    self.assertRaises(ValueError):
                await func(**args)

    async def test_api_error(self):
        with self.mock_http(lambda req: httpx.Response(404)):
            with self.assertRaises(httpx.HTTPStatusError):
                await api.alphafold_prediction("P99999")
