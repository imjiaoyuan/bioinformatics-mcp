import unittest
from unittest.mock import patch

import httpx

from servers.metagenomics_mcp import api
from tests.helpers import HTTPTestCase


def handler(req):
    path, query = req.url.path, req.url.params
    if path == "/project":
        limit = int(query.get("limit", "10"))
        offset = int(query.get("offset", "0"))
        data = [
            {"id": "mgp3", "name": "Mediterranean Bathypelagic Habitat",
             "pi": "Francisco Rodríguez-Valera", "status": "public"},
            {"id": "mgp4", "name": "Alvinella Pompejana Epibiont Metagenome",
             "pi": "Stephen Cary", "status": "public"},
        ]
        return httpx.Response(200, json={"data": data[offset:offset + limit],
                                         "total_count": 2, "limit": limit,
                                         "offset": offset, "prev": None, "next": None})
    if path == "/project/mgp3":
        return httpx.Response(200, json={"id": "mgp3", "name": "Mediterranean Bathypelagic Habitat",
                                         "pi": "Francisco Rodríguez-Valera", "status": "public"})
    if path == "/project/mgp40437":
        return httpx.Response(401, json={"ERROR": "insufficient permissions to view this data"})
    if path == "/project/mgp999999999":
        return httpx.Response(404, json={"ERROR": "id 999999999 does not exist"})
    if path == "/project/mgp5":
        return httpx.Response(200, json={"ERROR": "invalid value for option verbosity"})
    if path == "/metagenome/mgm4447943.3":
        return httpx.Response(200, json={"id": "mgm4447943.3", "name": "CA_04P",
                                         "project": ["mgp128"], "sample": ["mgs25823"]})
    if path == "/metagenome/mgm1":
        return httpx.Response(401, json={"ERROR": "insufficient permissions to view this data"})
    if path == "/sample/mgs100133":
        return httpx.Response(200, json={"id": "mgs100133", "name": "RU7", "version": 1})
    if path == "/annotation/sequence/mgm4447943.3":
        if query.get("source") not in (None, "RefSeq"):
            return httpx.Response(400, json={"ERROR": "invalid source"})
        body = ("sequence id\tm5nr id (md5sum)\tdna sequence\tsemicolon separated list of annotations\n"
                "mgm4447943.3|read1\t00001654ec8a922a5583f1f2612ad025\tACGT\tArcanobacterium haemolyticum DSM 20595\n"
                "mgm4447943.3|read2\t00007f2b56700f4d0a6b02136ba44a5a\tACGT\tClostridium botulinum A str. ATCC 3502; Clostridium botulinum A str. Hall\n")
        return httpx.Response(200, text=body)
    return httpx.Response(404)


class MetagenomicsTests(HTTPTestCase):
    async def test_projects_and_details(self):
        with self.mock_http(handler), patch("common.http.asyncio.sleep", new_callable=unittest.mock.AsyncMock):
            projects = await api.mgrast_projects(limit=1, offset=1)
            self.assertEqual(len(projects["projects"]), 1)
            self.assertEqual(projects["projects"][0]["id"], "mgp4")
            self.assertEqual(projects["total_count"], 2)
            self.assertEqual(projects["limit"], 1)
            self.assertEqual(projects["offset"], 1)
            project = await api.mgrast_project("MGP3")
            self.assertEqual(project["pi"], "Francisco Rodríguez-Valera")
            self.assertIn("source_url", project)
            metagenome = await api.mgrast_metagenome("mgm4447943.3")
            self.assertEqual(metagenome["name"], "CA_04P")
            sample = await api.mgrast_sample("mgs100133")
            self.assertEqual(sample["name"], "RU7")

    async def test_annotation(self):
        with self.mock_http(handler), patch("common.http.asyncio.sleep", new_callable=unittest.mock.AsyncMock):
            result = await api.mgrast_annotation("mgm4447943.3", source="RefSeq",
                                                 evalue=5, limit=1, offset=0)
            self.assertEqual(result["pagination"], "local")
            self.assertEqual(result["total"], 2)
            self.assertEqual(result["evalue"], "e-5")
            self.assertEqual(len(result["results"]), 1)
            self.assertEqual(result["results"][0]["annotations"],
                             ["Arcanobacterium haemolyticum DSM 20595"])
            page2 = await api.mgrast_annotation("mgm4447943.3", limit=1, offset=1)
            self.assertEqual(page2["results"][0]["annotations"],
                             ["Clostridium botulinum A str. ATCC 3502", "Clostridium botulinum A str. Hall"])

    async def test_invalid_id_patterns(self):
        for func, args in [(api.mgrast_project, {"project_id": "mgm4447943.3"}),
                           (api.mgrast_project, {"project_id": "mgpX"}),
                           (api.mgrast_metagenome, {"metagenome_id": "mgp3"}),
                           (api.mgrast_metagenome, {"metagenome_id": "mgm..3"}),
                           (api.mgrast_sample, {"sample_id": "mgm4447943.3"}),
                           (api.mgrast_sample, {"sample_id": "mgs"}),
                           (api.mgrast_projects, {"limit": 0}),
                           (api.mgrast_projects, {"pi": ""}),
                           (api.mgrast_annotation, {"metagenome_id": "mgp3"}),
                           (api.mgrast_annotation, {"metagenome_id": "mgm4447943.3",
                                                    "annotation_type": "taxonomy"}),
                           (api.mgrast_annotation, {"metagenome_id": "mgm4447943.3",
                                                    "annotation_type": "function", "source": "RefSeq"}),
                           (api.mgrast_annotation, {"metagenome_id": "mgm4447943.3", "evalue": 0})]:
            with self.subTest(tool=func.__name__, args=args), self.assertRaises(ValueError):
                await func(**args)

    async def test_upstream_error_json(self):
        with self.mock_http(handler):
            with self.assertRaisesRegex(ValueError, "MG-RAST API error"):
                await api.mgrast_project("mgp5")

    async def test_permission_vs_missing(self):
        with self.mock_http(handler):
            with self.assertRaisesRegex(ValueError, "not publicly accessible"):
                await api.mgrast_project("mgp40437")
            with self.assertRaisesRegex(ValueError, "does not exist"):
                await api.mgrast_project("mgp999999999")
            with self.assertRaisesRegex(ValueError, "not publicly accessible"):
                await api.mgrast_metagenome("mgm1")
            with self.assertRaisesRegex(ValueError, "does not exist"):
                await api.mgrast_sample("mgs404")


if __name__ == "__main__":
    unittest.main()
