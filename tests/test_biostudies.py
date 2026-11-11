import httpx

from servers.biostudies_mcp import api
from tests.helpers import HTTPTestCase

STUDY = {"section": {"subsections": [{"files": [[{"type": "file", "path": "E-MTAB-1.sdrf.txt", "size": 20}]]}]}}


class BioStudiesTests(HTTPTestCase):
    async def test_search_record_files(self):
        def handler(req):
            if req.url.path.endswith("search"):
                self.assertEqual(req.url.params["pageSize"], "1")
                return httpx.Response(200, json={"hits": [{"accession": "E-MTAB-1"}]})
            return httpx.Response(200, json=STUDY)
        with self.mock_http(handler):
            self.assertEqual((await api.biostudies_search("rice", limit=1))["hits"][0]["accession"], "E-MTAB-1")
            self.assertIn("section", (await api.biostudies_record("E-MTAB-1"))["study"])
            self.assertTrue((await api.biostudies_files("E-MTAB-1"))["files"][0]["url"].endswith(".sdrf.txt"))

    async def test_sdrf_duplicate_headers_and_bounds(self):
        def handler(req):
            if "/files/" in req.url.path:
                return httpx.Response(200, text="Source Name\tComment[file]\tComment[file]\nleaf\ta\tb\nleaf2\tc\td\n")
            return httpx.Response(200, json=STUDY)
        with self.mock_http(handler):
            result = await api.biostudies_samples("E-MTAB-1", 1)
            self.assertEqual(result["rows"], [["leaf", "a", "b"]])
            self.assertEqual(result["columns"][1:], ["Comment[file]", "Comment[file]"])
            self.assertTrue(result["truncated"])

    async def test_validation_all_tools(self):
        for func, args in [(api.biostudies_search, {"query": ""}), (api.biostudies_record, {"accession": "../bad"}),
                           (api.biostudies_files, {"accession": "E-MTAB-1", "limit": 0}),
                           (api.biostudies_samples, {"accession": "E-MTAB-1", "limit": 201})]:
            with self.subTest(tool=func.__name__), self.assertRaises(ValueError):
                await func(**args)

    async def test_api_failure(self):
        with self.mock_http(lambda req: httpx.Response(404)):
            with self.assertRaises(httpx.HTTPStatusError):
                await api.biostudies_record("E-MTAB-1")

    async def test_unsafe_file_path(self):
        with self.assertRaises(ValueError):
            api._files({"type": "file", "path": "../../secret"}, "E-MTAB-1")
