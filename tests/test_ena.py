import httpx

from servers.ena_mcp import server
from tests.helpers import HTTPTestCase


class ENATests(HTTPTestCase):
    async def test_search_fields_record(self):
        def handler(req):
            if "browser/api" in req.url.path:
                return httpx.Response(200, text="<RUN_SET/>")
            self.assertEqual(req.url.params["result"], "read_run")
            return httpx.Response(200, json=[{"run_accession": "SRR1"}])
        with self.mock_http(handler):
            self.assertEqual((await server.ena_search("tax_tree(4530)"))["records"][0]["run_accession"], "SRR1")
            self.assertTrue((await server.ena_fields())["fields"])
            self.assertEqual((await server.ena_record("SRR1"))["xml"], "<RUN_SET/>")

    async def test_fastq_pairs_preserve_checksums(self):
        row = {"fastq_ftp": "ftp.sra.ebi.ac.uk/a;ftp.sra.ebi.ac.uk/b", "fastq_md5": "aa;bb", "fastq_bytes": "10;20"}
        with self.mock_http(lambda req: httpx.Response(200, json=[row])):
            files = (await server.ena_fastq("SRR1"))["runs"][0]["files"]
            self.assertEqual(files[1], {"url": "https://ftp.sra.ebi.ac.uk/b", "md5": "bb", "bytes": 20})

    async def test_validation_all_tools(self):
        for func, args in [(server.ena_search, {"query": ""}), (server.ena_fields, {"result": "bad"}),
                           (server.ena_record, {"accession": "../../bad"}), (server.ena_fastq, {"accession": "SRR1", "limit": 0})]:
            with self.subTest(tool=func.__name__), self.assertRaises(ValueError):
                await func(**args)

    async def test_api_failure(self):
        with self.mock_http(lambda req: httpx.Response(500)):
            with self.assertRaises(httpx.HTTPStatusError):
                await server.ena_search("tax_tree(4530)")
