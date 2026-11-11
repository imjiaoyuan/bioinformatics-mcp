from unittest.mock import AsyncMock, patch

import httpx

from servers.emdb_mcp import api
from tests.helpers import HTTPTestCase

ENTRY = {
    "_id": "604339ff",
    "emdb_id": "EMD-11605",
    "admin": {
        "title": "Respiratory chain supercomplex I1III2IV1 in rat heart mitochondria",
        "current_status": {"code": {"valueOf_": "REL"}, "date": "2021-03-10T00:00:00"},
        "key_dates": {"deposition": "2020-08-10T00:00:00"},
    },
    "sample": {"name": {"valueOf_": "Respiratory chain supercomplex I1III2IV1"}},
    "map": {
        "file": "emd_11605.map.gz",
        "format": "CCP4",
        "size_kbytes": 865,
        "dimensions": {"col": 60, "row": 60, "sec": 60},
        "pixel_spacing": {"x": {"units": "A", "valueOf_": "7.4"}},
        "contour_list": {"contour": [{"level": 3.5}]},
        "statistics": {"average": 0.1, "minimum": -4.3, "maximum": 9.0, "std": 1.3},
    },
    "interpretation": {
        "half_map_list": {"half_map": [{"file": "emd_11605_half_map_1.map.gz", "format": "CCP4"}]},
        "segmentation_list": {"segmentation": [{"file": "emd_11605_msk_1.map"}]},
    },
    "structure_determination_list": {
        "structure_determination": [{
            "method": "subtomogramAveraging",
            "image_processing": [{
                "final_reconstruction": {
                    "resolution": {"res_type": "BY AUTHOR", "units": "A", "valueOf_": "29.6"},
                    "resolution_method": "FSC 0.143 CUT-OFF",
                },
            }],
        }],
    },
}


class EMDBTests(HTTPTestCase):
    async def test_all_tools_success(self):
        paths = []
        def handler(req):
            paths.append(f"{req.url.path}?{req.url.params}")
            if req.url.path.startswith("/emdb/api/search"):
                self.assertEqual(req.url.params["rows"], "10")
                self.assertEqual(req.url.params["start"], "0")
                self.assertEqual(req.url.params["wt"], "json")
                return httpx.Response(200, json=[ENTRY])
            return httpx.Response(200, json=ENTRY)
        with self.mock_http(handler), patch("common.http.asyncio.sleep", new_callable=AsyncMock):
            entry = await api.emdb_entry("emd-11605")
            resolution = await api.emdb_resolution("EMD-11605")
            maps = await api.emdb_map_files("EMD-11605")
            search = await api.emdb_search('title:"apoferritin"', limit=10)
        self.assertEqual(entry["emdb_id"], "EMD-11605")
        self.assertEqual(entry["status"], "REL")
        self.assertEqual(resolution["resolutions"][0]["resolution"], "29.6")
        self.assertEqual(resolution["resolutions"][0]["resolution_method"], "FSC 0.143 CUT-OFF")
        files = [record["file"] for record in maps["map_files"]]
        self.assertEqual(files, ["emd_11605.map.gz", "emd_11605_msk_1.map",
                                 "emd_11605_half_map_1.map.gz"])
        self.assertEqual(maps["map_files"][0]["pixel_spacing"]["x"], "7.4")
        self.assertEqual(search["results"][0]["emdb_id"], "EMD-11605")
        self.assertEqual(search["results"][0]["resolutions"], ["29.6"])
        self.assertIn("/emdb/api/entry/EMD-11605?", paths[0])
        self.assertIn("source_url", entry)

    async def test_validation_all_tools(self):
        for func, args in [(api.emdb_entry, {"emdb_id": "11605"}),
                           (api.emdb_resolution, {"emdb_id": "EMDbad"}),
                           (api.emdb_map_files, {"emdb_id": "../EMD-11605"}),
                           (api.emdb_search, {"query": ""}),
                           (api.emdb_search, {"query": "x", "limit": 101}),
                           (api.emdb_search, {"query": "x", "offset": -1})]:
            with self.subTest(tool=func.__name__), self.assertRaises(ValueError):
                await func(**args)

    async def test_api_error(self):
        with self.mock_http(lambda req: httpx.Response(404)):
            with self.assertRaises(httpx.HTTPStatusError):
                await api.emdb_entry("EMD-99999999")
