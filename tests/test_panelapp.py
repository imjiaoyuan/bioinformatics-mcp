"""Mocked tests for the PanelApp MCP api."""
import httpx

from servers.panelapp_mcp import api
from tests.helpers import HTTPTestCase

PANELS = {"count": 1700, "next": "https://panelapp/api/v1/panels/?page=2&page_size=2", "previous": None,
          "results": [{"id": 1207, "name": "Acute intermittent porphyria", "version": "2.3",
                       "status": "public", "disease_group": "Gastrohepatology",
                       "relevant_disorders": ["Acute intermittent porphyria"],
                       "types": [{"name": "Rare disease"}]},
                      {"id": 510, "name": "Breast and ovarian cancer", "version": "4.1",
                       "status": "public", "disease_group": "Cancer",
                       "relevant_disorders": ["Breast cancer"], "types": [{"name": "Cancer"}]}]}
PANEL = {"id": 510, "name": "Breast and ovarian cancer", "version": "4.1", "status": "public",
         "disease_group": "Cancer", "relevant_disorders": ["Breast cancer"],
         "stats": {"number_of_genes": 22, "number_of_confirmed_genes": 18}}
GENES = {"count": 2, "next": None, "previous": None, "results": [
    {"entity_name": "BRCA1", "entity_type": "gene", "confidence_level": "4",
     "mode_of_inheritance": "MONOALLELIC, BIALLELIC", "mode_of_pathogenicity": None,
     "phenotypes": ["Breast-ovarian cancer, familial 1"], "publications": [12345],
     "evidence": ["Expert Review"], "tags": [], "panel": 510,
     "gene_data": {"gene_symbol": "BRCA1", "hgnc_id": "HGNC:1100"}},
    {"entity_name": "BRCA2", "entity_type": "gene", "confidence_level": "3",
     "mode_of_inheritance": "MONOALLELIC", "mode_of_pathogenicity": None,
     "phenotypes": [], "publications": [], "evidence": ["Expert Review"], "tags": [],
     "panel": 510, "gene_data": {"gene_symbol": "BRCA2", "hgnc_id": "HGNC:1101"}}]}
GENE_PANELS = {"count": 28, "next": None, "previous": None, "results": [
    {"panel": 510, "confidence_level": "4", "mode_of_inheritance": "MONOALLELIC",
     "phenotypes": ["Breast-ovarian cancer"], "gene_data": {"gene_symbol": "BRCA1"}}]}


class PanelAppTests(HTTPTestCase):
    async def test_panels_panel_genes_and_gene(self):
        seen = []

        def handler(req):
            seen.append((req.method, req.url.path, dict(req.url.params)))
            if req.url.path.endswith("/panels/"):
                self.assertEqual(req.url.params["page"], "1")
                self.assertEqual(req.url.params["page_size"], "2")
                return httpx.Response(200, json=PANELS)
            if req.url.path.endswith("/panels/510/"):
                return httpx.Response(200, json=PANEL)
            if req.url.path.endswith("/panels/510/genes/"):
                self.assertEqual(req.url.params["confidence_levels"], "3&4")
                return httpx.Response(200, json=GENES)
            if req.url.path.endswith("/genes/BRCA1/"):
                return httpx.Response(200, json=GENE_PANELS)
            raise AssertionError(f"unexpected request: {req.url.path}")

        with self.mock_http(handler):
            panels = await api.panelapp_panels(page_index=1, page_size=2)
            self.assertEqual(panels["total"], 1700)
            self.assertEqual(panels["results"][0]["id"], 1207)
            detail = await api.panelapp_panel("510")
            self.assertEqual(detail["stats"]["number_of_genes"], 22)
            genes = await api.panelapp_panel_genes("510", limit=1)
            self.assertEqual(genes["results"][0]["gene_symbol"], "BRCA1")
            self.assertEqual(genes["results"][0]["confidence_level"], "4")
            self.assertTrue(genes["truncated"])
            gene = await api.panelapp_gene("brca1")
            self.assertEqual(gene["total"], 28)
            self.assertEqual(gene["results"][0]["panel"], 510)
        self.assertEqual(seen[3][0], "GET")

    async def test_name_filter_and_missing_panel(self):
        with self.mock_http(lambda req: httpx.Response(200, json=PANELS)):
            panels = await api.panelapp_panels(name="porphyria", page_index=1, page_size=2)
            self.assertEqual(len(panels["results"]), 1)
            self.assertEqual(panels["results"][0]["id"], 1207)
        with self.mock_http(lambda req: httpx.Response(200, json={"detail": "Not found."})):
            with self.assertRaises(ValueError):
                await api.panelapp_panel("999999")

    async def test_validation_before_network(self):
        cases = [(api.panelapp_panels, {"name": "x" * 201}),
                 (api.panelapp_panels, {"page_index": 0}),
                 (api.panelapp_panels, {"page_size": 101}),
                 (api.panelapp_panel, {"panel_id": "bad"}),
                 (api.panelapp_panel_genes, {"panel_id": "510", "confidence_levels": "5"}),
                 (api.panelapp_panel_genes, {"panel_id": "510", "confidence_levels": "4,4.5"}),
                 (api.panelapp_panel_genes, {"panel_id": "510", "limit": 0}),
                 (api.panelapp_gene, {"gene_symbol": "BRCA1!"}),
                 (api.panelapp_gene, {"gene_symbol": "1BRCA"})]
        for func, kwargs in cases:
            with self.subTest(tool=func.__name__, kwargs=kwargs), self.assertRaises(ValueError):
                await func(**kwargs)

    async def test_api_error(self):
        with self.mock_http(lambda req: httpx.Response(500)):
            with self.assertRaises(httpx.HTTPStatusError):
                await api.panelapp_panels()
