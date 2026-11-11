from unittest.mock import AsyncMock, patch

import httpx

from servers.depmap_mcp import api
from tests.helpers import HTTPTestCase


def _route(handler_map):
    def handler(req):
        for fragment, action in handler_map.items():
            if fragment in req.url.path:
                return action(req)
        return httpx.Response(404)

    return handler


class DepMapTests(HTTPTestCase):
    async def test_all_tools_success(self):
        datasets = [{"id": "OmicsExpressionProteinCodingGenes21Q2", "display_name": "Expression",
                     "data_type": "expression", "download_entry_url": "https://x/y"}]
        curves = {"curve_params": [{"depmap_id": "ACH-000001", "ec50": 0.5, "auc": 0.9}]}
        summary = {"drc_dataset_options": [{"id": "Prism_oncology_per_curve"}]}
        def handler(req):
            path = req.url.path
            if path.endswith("/download/datasets"):
                return httpx.Response(200, json=datasets)
            if "compound_sensitivity" in path:
                self.assertEqual(req.url.path.split("/")[-1], "ACH-000001")
                return httpx.Response(200, json={"data": [{"compound_label": "geldanamycin"}]})
            if "cell_line/datasets" in path:
                return httpx.Response(200, json={"expression": [{"display_name": "CCLE expression"}]})
            if "gene_characterization_data" in path:
                return httpx.Response(200, json=[{"id": "OncoTarget", "display_name": "Onco Target"}])
            if "data_availability_metadata" in path:
                return httpx.Response(200, json={"Prism_oncology_per_curve": {"priority": 1}})
            if "prioritized_dataset" in path:
                self.assertEqual(req.url.params["compound_id"], "BRD-K19558315")
                return httpx.Response(200, json={"auc_dataset_label": "Prism_oncology_per_curve"})
            if "compound_summary" in path:
                return httpx.Response(200, json=summary)
            if "dose_curve_data" in path:
                self.assertEqual(req.url.params["drc_dataset_label"], "Prism_oncology_per_curve")
                return httpx.Response(200, json=curves)
            return httpx.Response(404)

        with self.mock_http(handler), patch("common.http.asyncio.sleep", new_callable=AsyncMock):
            listing = await api.depmap_datasets(limit=2)
            self.assertEqual(listing["results"], datasets)
            self.assertEqual(listing["pagination"], "local")
            self.assertEqual(listing["source_url"], api.API_BASE + "/download/datasets")
            self.assertEqual((await api.depmap_cell_line_sensitivity("ach-000001"))["source_url"],
                             api.PORTAL_BASE + "/cell_line/compound_sensitivity/ACH-000001")
            self.assertEqual((await api.depmap_cell_line_datasets("ACH-000001")),
                             {"source_url": api.PORTAL_BASE + "/cell_line/datasets/ACH-000001",
                              "expression": [{"display_name": "CCLE expression"}]})
            gene = await api.depmap_gene_characterization("TP53")
            self.assertEqual(gene["source_url"], api.PORTAL_BASE + "/gene/gene_characterization_data/TP53")
            self.assertIn("source_url", await api.depmap_compound_availability())
            drc = await api.depmap_compound_drc_dataset("Geldanamycin", "BRD-K19558315")
            self.assertEqual(drc["auc_dataset_label"], "Prism_oncology_per_curve")
            self.assertEqual((await api.depmap_compound_summary("Geldanamycin", "BRD-K19558315")),
                             {"source_url": api.API_BASE + "/compound/compound_summary", **summary})
            self.assertEqual((await api.depmap_compound_dose_curves(
                "BRD-K19558315", "Prism_oncology_per_curve", "Prism_oncology_dose_replicate"))["curve_params"],
                curves["curve_params"])

    async def test_validation_all_tools(self):
        cases = [
            (api.depmap_datasets, {"limit": 101}),
            (api.depmap_datasets, {"offset": 1_000_001}),
            (api.depmap_cell_line_sensitivity, {"depmap_id": "A1"}),
            (api.depmap_cell_line_datasets, {"depmap_id": "../etc"}),
            (api.depmap_gene_characterization, {"gene_symbol": "1TP53"}),
            (api.depmap_gene_characterization, {"gene_symbol": "A" * 60}),
            (api.depmap_compound_drc_dataset, {"compound_label": "", "compound_id": "BRD-K1"}),
            (api.depmap_compound_summary, {"compound_label": "x", "compound_id": "a" * 200}),
            (api.depmap_compound_dose_curves, {"compound_id": "BRD-K1", "drc_dataset_label": "a",
                                                  "replicate_dataset_name": ""}),
        ]
        for func, args in cases:
            with self.subTest(tool=func.__name__), self.assertRaises(ValueError):
                await func(**args)

    async def test_api_error(self):
        with self.mock_http(_route({})), patch("common.http.asyncio.sleep", new_callable=AsyncMock):
            with self.assertRaises(httpx.HTTPStatusError):
                await api.depmap_cell_line_sensitivity("ACH-999999")

    async def test_too_large_response(self):
        def handler(req):
            return httpx.Response(200, json=[{"id": "d" * 20_000}] * 2000)
        with self.mock_http(handler), patch("common.http.asyncio.sleep", new_callable=AsyncMock):
            with self.assertRaises(ValueError):
                await api.depmap_datasets()
