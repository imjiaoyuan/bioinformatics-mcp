import httpx
from unittest.mock import AsyncMock, patch

from servers.hpa_mcp import api
from tests.helpers import HTTPTestCase


def mock_sleep():
    return patch("common.http.asyncio.sleep", new_callable=AsyncMock)

ROW = {
    "Gene": "TP53", "Gene synonym": ["LFS1", "p53"], "Ensembl": "ENSG00000141510",
    "Gene description": "Tumor protein p53", "Uniprot": ["P04637"], "Chromosome": "17",
    "Position": "7661779-7687538",
    "Protein class": ["Cancer-related genes", "Disease related genes"],
    "Biological process": ["Apoptosis"], "Molecular function": ["DNA-binding"],
    "Disease involvement": ["Li-Fraumeni syndrome"], "Evidence": "Evidence at protein level",
    "HPA evidence": "Evidence at protein level", "UniProt evidence": "Evidence at protein level",
    "NeXtProt evidence": "Evidence at protein level", "Antibody": ["HPA051244"],
    "RNA tissue specificity": "Low tissue specificity", "RNA tissue distribution": "Detected in all",
    "RNA tissue specificity score": None, "RNA tissue specific nTPM": {"liver": "95.3"},
    "Protein tissue specificity": "Not detected", "Protein tissue distribution": "Not detected",
    "Protein tissue specificity score": None, "Protein tissue specific Intensity": None,
    "Reliability (IH)": "Enhanced", "Tissue expression cluster": "Cluster 54: Non-specific - Ribosome",
    "RNA tissue cell type enrichment": ["Stomach - Mitotic cells (Stomach)"],
    "RNA single cell type specificity": "Low cell type specificity",
    "RNA single cell type distribution": "Detected in many",
    "RNA single cell type specificity score": None, "RNA single cell type specific nCPM": None,
    "RNA single cell type group specificity": "Low cell type specificity",
    "RNA single cell type group distribution": "Detected in many",
    "RNA single cell type group specificity score": None,
    "RNA single cell type group specific nCPM": None,
    "RNA cell line specificity": "Low cancer specificity",
    "RNA cell line distribution": "Detected in all", "RNA cell line specificity score": None,
    "RNA cell line specific nTPM": None, "Protein cell type specificity": "Not detected",
    "Protein cell type distribution": "Not detected", "Protein cell type specificity score": None,
    "Protein cell type specific Intensity": None, "Reliability (IF)": "Enhanced",
    "Single cell expression cluster": "Cluster 65: Non-specific - Cell growth & division",
    "Cell line expression cluster": "Cluster 42: Non-specific - Unknown function",
    "Subcellular location": ["Nucleoplasm", "Vesicles", "Cytosol"],
    "Subcellular main location": ["Nucleoplasm"],
    "Subcellular additional location": ["Vesicles", "Cytosol"],
    "Secretome location": None, "Secretome function": None, "CCD Protein": "Yes",
    "CCD Transcript": "No",
    "RNA cancer specificity": "Low cancer specificity", "RNA cancer distribution": "Detected in all",
    "RNA cancer specificity score": None, "RNA cancer specific pTPM": None,
    "Blood concentration - Conc. blood IM [pg/L]": None,
    "Blood concentration - Conc. blood MS [pg/L]": None,
    "Cancer prognostics - Breast Invasive Carcinoma (validation)": {
        "prognostic": "potential prognostic", "is_prognostic": True, "p_val": "5.06e-4"},
    "Subcellular unrelated": "keep out",
}
OTHER = {"Gene": "TP53INP1", "Ensembl": "ENSG00000164938", "RNA tissue specificity": "Tissue enhanced"}
QUERY_PATH = "/search/Gene:TP53"


class HPATests(HTTPTestCase):
    async def test_search(self):
        def handler(req):
            self.assertEqual(req.url.params["format"], "json")
            self.assertEqual(req.url.params["compress"], "no")
            return httpx.Response(200, json=[ROW, OTHER])
        with self.mock_http(handler), \
                mock_sleep():
            result = await api.hpa_search("Gene:TP53", limit=1, offset=1)
        self.assertEqual(result["results"], [OTHER])
        self.assertEqual(result["total"], 2)
        self.assertFalse(result["truncated"])
        with self.mock_http(lambda req: httpx.Response(200, json=[ROW, OTHER])), mock_sleep():
            flagged = await api.hpa_search("Gene:TP53", limit=1, offset=0)
        self.assertTrue(flagged["truncated"])
        self.assertEqual(result["pagination"], "local")
        self.assertIn("proteinatlas.org", result["source_url"])

    async def test_gene_tools(self):
        def handler(req):
            self.assertEqual(req.url.path, QUERY_PATH)
            return httpx.Response(200, json=[ROW, OTHER])
        with self.mock_http(handler), mock_sleep():
            gene = await api.hpa_gene("tp53")
            tissue = await api.hpa_tissue_expression("TP53")
            cell = await api.hpa_cell_expression("TP53")
            subcell = await api.hpa_subcellular_location("TP53")
            pathology = await api.hpa_pathology("TP53")
        self.assertEqual(gene["gene"], "TP53")
        self.assertEqual(gene["Ensembl"], "ENSG00000141510")
        self.assertEqual(gene["gene_url"], "https://www.proteinatlas.org/TP53")
        self.assertEqual(tissue["RNA tissue specific nTPM"], {"liver": "95.3"})
        self.assertNotIn("Subcellular main location", tissue)
        self.assertNotIn("Reliability (IF)", cell)
        self.assertEqual(subcell["Reliability (IF)"], "Enhanced")
        self.assertEqual(subcell["Subcellular main location"], ["Nucleoplasm"])
        self.assertNotIn("RNA tissue specificity", subcell)
        self.assertEqual(pathology["cancer_prognostics"]["Breast Invasive Carcinoma (validation)"]["is_prognostic"], True)
        self.assertEqual(pathology["RNA cancer distribution"], "Detected in all")
        for result in (gene, tissue, cell, subcell, pathology):
            self.assertIn("source_url", result)

    async def test_unknown_gene(self):
        with self.mock_http(lambda req: httpx.Response(200, json=[OTHER])), mock_sleep():
            with self.assertRaises(ValueError):
                await api.hpa_gene("TP53")

    async def test_unexpected_payload(self):
        with self.mock_http(lambda req: httpx.Response(200, json={"oops": True})), mock_sleep():
            with self.assertRaises(ValueError):
                await api.hpa_search("TP53")

    async def test_validation_all_tools(self):
        cases = [(api.hpa_search, {"query": ""}), (api.hpa_search, {"query": "x", "limit": 101}),
                 (api.hpa_search, {"query": "x", "offset": -1}),
                 (api.hpa_gene, {"gene": "bad gene!"}),
                 (api.hpa_tissue_expression, {"gene": ""}),
                 (api.hpa_cell_expression, {"gene": "../etc"}),
                 (api.hpa_subcellular_location, {"gene": "x" * 151}),
                 (api.hpa_pathology, {"gene": "p53;drop"})]
        for func, kwargs in cases:
            with self.subTest(tool=func.__name__), self.assertRaises(ValueError):
                await func(**kwargs)

    async def test_api_error(self):
        with self.mock_http(lambda req: httpx.Response(404)), mock_sleep():
            with self.assertRaises(httpx.HTTPStatusError):
                await api.hpa_gene("TP53")
