from unittest.mock import AsyncMock, patch

import httpx

from servers.ucsc_mcp import api
from tests.helpers import HTTPTestCase


class UCSCTests(HTTPTestCase):
    async def test_success_all_tools(self):
        paths = []

        def handler(req):
            paths.append(req.url.path)
            params = req.url.params
            if req.url.path.endswith("list/ucscGenomes"):
                return httpx.Response(200, json={"ucscGenomes": {
                    "hg38": {"name": "Human", "organism": "Homo sapiens"},
                    "mm39": {"name": "Mouse, broad institute"},
                }})
            if req.url.path.endswith("list/tracks"):
                self.assertEqual(params["genome"], "hg38")
                return httpx.Response(200, json={"hg38": {"knownGene": {"shortLabel": "Genes"}}})
            if req.url.path.endswith("list/chromosomes"):
                return httpx.Response(200, json={"chromosomes": {"chr1": {"len": 248956422}}})
            self.assertEqual((params["genome"], params["track"]), ("hg38", "knownGene"))
            self.assertEqual((params["chrom"], params["start"], params["end"]),
                             ("chr1", "10000", "20000"))
            return httpx.Response(200, json={"knownGene": [
                {"chrom": "chr1", "txStart": 11873, "txEnd": 14409, "name": "uc010nxq.1"}]})

        with self.mock_http(handler), patch("common.http.asyncio.sleep", new_callable=AsyncMock):
            self.assertIn("hg38", (await api.ucsc_list_genomes())["ucscGenomes"])
            self.assertIn("knownGene", (await api.ucsc_list_tracks("hg38"))["hg38"])
            self.assertEqual((await api.ucsc_list_chromosomes("hg38"))["chromosomes"]["chr1"]["len"], 248956422)
            record = (await api.ucsc_get_data("hg38", "knownGene", "chr1", 10000, 20000))["knownGene"][0]
            self.assertEqual(record["name"], "uc010nxq.1")
            self.assertEqual((await api.ucsc_search_genomes("homo"))["ucscGenomes"], {"hg38": {"name": "Human", "organism": "Homo sapiens"}})
        for suffix in ["list/ucscGenomes", "list/tracks", "list/chromosomes", "getData/track"]:
            self.assertTrue(any(p.endswith(suffix) for p in paths))

    async def test_search_genomes_filters_by_key(self):
        payload = {"ucscGenomes": {"sacCer3": {"name": "S. cerevisiae"}}}
        with self.mock_http(lambda req: httpx.Response(200, json=payload)), \
                patch("common.http.asyncio.sleep", new_callable=AsyncMock):
            self.assertEqual((await api.ucsc_search_genomes("saccer"))["ucscGenomes"], payload["ucscGenomes"])
            self.assertEqual((await api.ucsc_search_genomes("zzz"))["matched"], 0)

    async def test_validation_all_tools(self):
        cases = [
            (api.ucsc_list_tracks, {"genome": "bad genome"}),
            (api.ucsc_list_chromosomes, {"genome": "../human"}),
            (api.ucsc_get_data, {"genome": "hg38", "track": "knownGene", "chrom": "notchrom1", "start": 0, "end": 100}),
            (api.ucsc_get_data, {"genome": "hg38", "track": "knownGene", "chrom": "chr1", "start": -1, "end": 100}),
            (api.ucsc_get_data, {"genome": "hg38", "track": "knownGene", "chrom": "chr1", "start": 100, "end": 100}),
            (api.ucsc_get_data, {"genome": "hg38", "track": "knownGene", "chrom": "chr1", "start": 100, "end": 99999999999999}),
            (api.ucsc_search_genomes, {"name": ""}),
            (api.ucsc_search_genomes, {"name": "x" * 101}),
        ]
        for func, args in cases:
            with self.subTest(tool=func.__name__), self.assertRaises(ValueError):
                await func(**args)

    async def test_api_error(self):
        with self.mock_http(lambda req: httpx.Response(404)):
            with self.assertRaises(httpx.HTTPStatusError):
                await api.ucsc_get_data("hg38", "missingTrack", "chr1", 0, 100)
