import gzip
from unittest.mock import AsyncMock, patch

import httpx

from servers.panglao_mcp import server
from tests.helpers import HTTPTestCase

TSV = "\n".join([
    "species\tofficial gene symbol\tcell type\tnicknames\tubiquitousness index\t"
    "product description\tgene type\tcanonical marker\tgerm layer\torgan\t"
    "sensitivity_human\tsensitivity_mouse\tspecificity_human\tspecificity_mouse",
    "Mm Hs\tPTF1A\tAcinar cells\tPTF1-p48\t0.001\tpancreas associated transcription factor 1a\t"
    "protein-coding gene\t1\tEndoderm\tPancreas\t0.0\t0.157143\t0.000628931\t0.000773445",
    "Mm\tKrt8\tAcinar cells\tK8|Keratin-8\t0.0\tkeratin 8\tprotein-coding gene\t0\tEctoderm\t"
    "Pancreas\t0.5\t0.5\t0.1\t0.1",
    "Mm Hs\tPECAM1\tEndothelial cells\tCD31\t0.004\tplatelet and endothelial cell adhesion molecule\t"
    "protein-coding gene\t1\tMesoderm\tVasculature\t0.9\t0.9\t0.01\t0.01",
])


def gzip_handler(req, status=200):
    if status != 200:
        return httpx.Response(status)
    return httpx.Response(200, headers={"Content-Type": "application/octet-stream"},
                          content=gzip.compress(TSV.encode()))


class PanglaoTests(HTTPTestCase):
    async def test_all_tools_success(self):
        with self.mock_http(gzip_handler), patch("common.http.asyncio.sleep", new_callable=AsyncMock):
            cell_types = await server.panglao_cell_types(limit=1, offset=1)
            self.assertEqual(cell_types["source_url"], server.MARKERS_URL)
            self.assertEqual(cell_types["pagination"], "local")
            self.assertEqual(cell_types["total"], 2)
            self.assertEqual(cell_types["results"][0]["cell_type"], "Endothelial cells")

            markers = await server.panglao_cell_type_markers("acinar cells", species="human")
            self.assertEqual([row["gene"] for row in markers["results"]], ["PTF1A"])

            gene = await server.panglao_gene_markers("pecam1")
            self.assertEqual(gene["gene"], "PECAM1")
            self.assertEqual(gene["results"][0]["cell_type"], "Endothelial cells")

            organ = await server.panglao_markers_by_organ("pancreas", canonical_only=True,
                                                          species="mouse")
            self.assertEqual([row["gene"] for row in organ["results"]], ["PTF1A"])

            search = await server.panglao_search_markers("cd31")
            self.assertEqual(search["results"][0]["nicknames"], "CD31")

    async def test_unknown_cell_type_and_organ(self):
        with self.mock_http(gzip_handler), patch("common.http.asyncio.sleep", new_callable=AsyncMock):
            with self.assertRaises(ValueError):
                await server.panglao_cell_type_markers("Neurons")
            with self.assertRaises(ValueError):
                await server.panglao_markers_by_organ("Brain")

    async def test_validation_all_tools(self):
        for func, args in [(server.panglao_cell_types, {"species": "plant"}),
                           (server.panglao_cell_type_markers, {"cell_type": ""}),
                           (server.panglao_gene_markers, {"gene": "bad gene"}),
                           (server.panglao_markers_by_organ, {"organ": "x", "species": "fungus"}),
                           (server.panglao_search_markers, {"query": "x", "limit": 101})]:
            with self.subTest(tool=func.__name__), self.assertRaises(ValueError):
                await func(**args)

    async def test_api_error(self):
        with self.mock_http(lambda req: gzip_handler(req, status=404)):
            with self.assertRaises(httpx.HTTPStatusError):
                await server.panglao_cell_types()
