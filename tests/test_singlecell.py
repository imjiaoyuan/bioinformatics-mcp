import json
from unittest.mock import AsyncMock, patch

import httpx

from servers.singlecell_mcp import server
from tests.helpers import HTTPTestCase


class SingleCellTests(HTTPTestCase):
    async def test_all_tools_success(self):
        azul_hits = [{"entryId": "74b6d569-3b11-42ef-b6b1-a0454522b4a0",
                      "projects": [{"projectTitle": "1M Neurons"}],
                      "termFacets": {"organ": {"terms": []}}}]
        def handler(req):
            path, params = req.url.path, req.url.params
            if path == "/index/projects" and "search_after" in params:
                return httpx.Response(200, json={"hits": azul_hits, "pagination": {"next": None, "total": 1}})
            if path == "/index/projects" and params["filters"]:
                self.assertEqual(json.loads(params["filters"]), {"organ": {"is": ["blood"]}})
                return httpx.Response(200, json={"hits": azul_hits, "pagination": {"total": 86}})
            if path.startswith("/index/projects/"):
                self.assertEqual(path.rsplit("/", 1)[1], "74b6d569-3b11-42ef-b6b1-a0454522b4a0")
                return httpx.Response(200, json={"entryId": "74b6d569-3b11-42ef-b6b1-a0454522b4a0"})
            if path == "/single_cell/api/v1/search":
                self.assertEqual(params["terms"], "immune")
                self.assertEqual(params["page"], "2")
                return httpx.Response(200, json={"type": "study", "total_studies": 172,
                                                 "matching_accessions": ["SCP2554"]})
            if path.endswith("/annotations/broad_group"):
                return httpx.Response(200, json={"name": "broad_group", "scope": "cluster", "values": ["Neuron"]})
            if path.endswith("/annotations"):
                return httpx.Response(200, json=[{"name": "CLUSTER", "type": "group", "values": ["DG"]}])
            if path.endswith("/clusters"):
                return httpx.Response(200, json=["Coordinates_CA1"])
            if path.endswith("/site/studies/SCP1"):
                return httpx.Response(200, json={"accession": "SCP1", "study_files": []})
            raise AssertionError(path)
        with self.mock_http(handler), patch("common.http.asyncio.sleep", new_callable=AsyncMock):
            search = await server.hca_search(field="organ", value="blood", limit=10)
            self.assertEqual(search["pagination"]["total"], 86)
            self.assertNotIn("termFacets", search)
            self.assertEqual(search["source_url"], "https://service.azul.data.humancellatlas.org/index/projects"
                                                 "?size=10&filters=%7B%22organ%22%3A+%7B%22is%22%3A+%5B%22blood%22%5D%7D%7D")
            cursor_page = await server.hca_search(limit=10, cursor='["1M Neurons", "abc"]')
            self.assertEqual(cursor_page["hits"][0]["projects"][0]["projectTitle"], "1M Neurons")
            project = await server.hca_project("74B6D569-3B11-42EF-B6B1-A0454522B4A0")
            self.assertEqual(project["entryId"], "74b6d569-3b11-42ef-b6b1-a0454522b4a0")
            self.assertEqual((await server.scp_search_studies("immune", page_number=2))["matching_accessions"], ["SCP2554"])
            self.assertEqual((await server.scp_study_annotations("scp1"))["results"][0]["name"], "CLUSTER")
            self.assertEqual((await server.scp_study_annotation("SCP1", "broad_group"))["scope"], "cluster")
            self.assertEqual((await server.scp_study_clusters("SCP1"))["results"][0], "Coordinates_CA1")
            self.assertEqual((await server.scp_study_files_summary("SCP1"))["accession"], "SCP1")

    async def test_validation_all_tools(self):
        for func, args in [
            (server.hca_search, {"entity": "cells"}),
            (server.hca_search, {"field": "organ"}),
            (server.hca_search, {"value": "blood"}),
            (server.hca_search, {"limit": 51}),
            (server.hca_project, {"project_uuid": "not-a-uuid"}),
            (server.scp_search_studies, {"query": ""}),
            (server.scp_search_studies, {"query": "immune", "page_number": 1001}),
            (server.scp_study_annotations, {"accession": "ABC1"}),
            (server.scp_study_annotation, {"accession": "SCP1", "annotation": ""}),
            (server.scp_study_clusters, {"accession": "SCP;1"}),
            (server.scp_study_files_summary, {"accession": "scp"}),
        ]:
            with self.subTest(tool=func.__name__), self.assertRaises(ValueError):
                await func(**args)

    async def test_api_error(self):
        with self.mock_http(lambda req: httpx.Response(404)):
            with self.assertRaises(httpx.HTTPStatusError):
                await server.hca_project("74b6d569-3b11-42ef-b6b1-a0454522b4a0")
