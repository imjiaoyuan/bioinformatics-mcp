import httpx

from servers.uniprot_mcp import server
from tests.helpers import HTTPTestCase


class UniProtTests(HTTPTestCase):
    async def test_search_pagination(self):
        with self.mock_http(lambda req: httpx.Response(200, json={"results": [{"primaryAccession": "P04637"}]},
                                                      headers={"Link": '<https://rest.uniprot.org/uniprotkb/search?cursor=x>; rel="next"'})):
            result = await server.uniprot_search("gene:TP53", 1)
            self.assertEqual(result["results"][0]["primaryAccession"], "P04637")
            self.assertIn("cursor=x", result["next_url"])

    async def test_entry_and_fasta(self):
        with self.mock_http(lambda req: httpx.Response(200, json={"primaryAccession": "P04637"}) if req.url.path.endswith("json") else httpx.Response(200, text=">P04637\nMEEP")):
            self.assertEqual((await server.uniprot_entry("P04637"))["record"]["primaryAccession"], "P04637")
            self.assertIn("MEEP", (await server.uniprot_sequence("P04637"))["fasta"])

    async def test_mapping_job_lifecycle(self):
        def handler(req):
            if req.method == "POST":
                self.assertIn(b"ids=7157%2C4193", req.content)
                return httpx.Response(200, json={"jobId": "job1"})
            if "status" in req.url.path:
                return httpx.Response(200, json={"results": True})
            return httpx.Response(200, json={"results": [{"from": "7157", "to": "P04637"}], "failedIds": ["bad"]})
        with self.mock_http(handler):
            self.assertEqual((await server.uniprot_mapping_submit(["7157", "4193"]))["jobId"], "job1")
            self.assertTrue((await server.uniprot_mapping_status("job1"))["results"])
            self.assertEqual((await server.uniprot_mapping_results("job1"))["failedIds"], ["bad"])

    async def test_all_tool_validation(self):
        cases = [(server.uniprot_search, {"query": ""}), (server.uniprot_entry, {"accession": "bad"}),
                 (server.uniprot_sequence, {"accession": "../P04637"}), (server.uniprot_mapping_submit, {"ids": []}),
                 (server.uniprot_mapping_status, {"job_id": "../job"}), (server.uniprot_mapping_results, {"job_id": "job1", "limit": 0})]
        for func, args in cases:
            with self.subTest(tool=func.__name__), self.assertRaises(ValueError):
                await func(**args)

    async def test_missing_entry(self):
        with self.mock_http(lambda req: httpx.Response(404)):
            with self.assertRaises(httpx.HTTPStatusError):
                await server.uniprot_entry("P04637")
