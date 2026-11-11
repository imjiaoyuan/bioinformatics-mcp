import os
from unittest.mock import AsyncMock, patch

import httpx

from servers.sra_mcp import api
from tests.helpers import HTTPTestCase

EXPSUM = {
    "uid": "8",
    "expxml": '<Summary><Title>Human HapMap genomic library</Title>'
              '<Platform instrument_model="454 GS FLX">LS454</Platform>'
              '<Statistics total_spots="3325405"/>'
              '<Experiment acc="SRX000007"/><Study acc="SRP000001" name="Structural variation"/>'
              '<Sample acc="SRS000100"/><Organism taxid="9606" ScientificName="Homo sapiens"/>'
              '<Library_descriptor><LIBRARY_LAYOUT><PAIRED NOMINAL_LENGTH="3000"/></LIBRARY_LAYOUT></Library_descriptor>'
              '<Bioproject>PRJNA33627</Bioproject></Summary>',
    "runs": '<Run acc="SRR000001" total_spots="470985"/><Run acc="SRR000013" total_spots="478304"/>',
}


class SRATests(HTTPTestCase):
    async def test_pagination_uses_entrez_parameters_and_reports_remaining_pages(self):
        def handler(req):
            self.assertEqual(req.url.params["retmax"], "2")
            self.assertNotIn("limit", req.url.params)
            self.assertNotIn("offset", req.url.params)
            start = int(req.url.params["retstart"])
            ids = ["1", "2", "3", "4"][start:start + 2]
            return httpx.Response(200, json={"esearchresult": {"count": "4", "idlist": ids}})
        with patch.dict(os.environ, {"NCBI_EMAIL": "test@example.invalid", "NCBI_API_KEY": "TEST_SECRET"}), self.mock_http(handler):
            first = await api.sra_search("human", limit=2)
            second = await api.sra_search("human", limit=2, offset=first["next_offset"])
        self.assertEqual(first["uids"], ["1", "2"])
        self.assertEqual(second["uids"], ["3", "4"])
        self.assertFalse(second["truncated"])

    async def test_study_pagination_counts_upstream_experiments(self):
        async def get(endpoint, params):
            if endpoint == "esearch":
                return {"esearchresult": {"count": "8", "idlist": ["8"]}}
            return {"result": {"8": EXPSUM}}
        with patch.object(api, "_get", side_effect=get):
            result = await api.sra_studies("human", limit=1)
        self.assertTrue(result["truncated"])
        self.assertEqual(result["next_offset"], 1)
        self.assertEqual(result["total_kind"], "studies_in_this_page")

    async def test_source_url_is_redacted_and_sibling_xml_fragments_are_parsed(self):
        summary = dict(EXPSUM, expxml='<Summary><Title>Example</Title><Platform instrument_model="NovaSeq">ILLUMINA</Platform></Summary>'
                       '<Study acc="SRP1"/><Organism ScientificName="Homo sapiens"/>')
        def handler(req):
            self.assertEqual(req.url.params["api_key"], "TEST_SECRET")
            return httpx.Response(200, json={"result": {"1": summary}})
        with patch.dict(os.environ, {"NCBI_EMAIL": "test@example.invalid", "NCBI_API_KEY": "TEST_SECRET"}), self.mock_http(handler):
            result = await api._get("esummary", {"id": "1"})
        self.assertNotIn("TEST_SECRET", result["source_url"])
        self.assertNotIn("email=", result["source_url"])
        parsed = api._summarize(summary)
        self.assertEqual(parsed["title"], "Example")
        self.assertEqual(parsed["study"][0]["acc"], "SRP1")
        self.assertEqual(parsed["instrument_model"], "NovaSeq")

    async def test_search_metadata_and_studies(self):
        def handler(req):
            params = req.url.params
            if "esearch" in req.url.path:
                self.assertEqual(params["db"], "sra")
                return httpx.Response(200, json={"esearchresult": {"count": "2", "idlist": ["8", "9"]}})
            self.assertEqual(params["email"], "researcher@example.org")
            return httpx.Response(200, json={"result": {"uids": ["8"], "8": EXPSUM}})
        with patch.dict(os.environ, {"NCBI_EMAIL": "researcher@example.org"}), \
             self.mock_http(handler), patch("common.http.asyncio.sleep", new_callable=AsyncMock):
            search = await api.sra_search('organism="Homo sapiens"', limit=5, offset=1)
            self.assertEqual(search["count"], 2)
            self.assertEqual(search["uids"], ["8", "9"])
            self.assertIn("source_url", search)
            metadata = await api.sra_run_metadata("srr000001")
            self.assertEqual(metadata["study"][0]["acc"], "SRP000001")
            self.assertEqual(metadata["organism"][0]["ScientificName"], "Homo sapiens")
            self.assertEqual(metadata["runs"][0]["acc"], "SRR000001")
            self.assertIn("source_url", metadata)
            studies = await api.sra_studies("human", limit=5)
            self.assertEqual(studies["count"], 2)
            self.assertEqual(len(studies["results"]), 1)
            self.assertEqual(studies["results"][0]["study_accession"], "SRP000001")
            self.assertEqual(studies["results"][0]["organisms"], ["Homo sapiens"])
            self.assertIn("source_url", studies)

    async def test_validation_all_tools(self):
        for func, kwargs in [(api.sra_search, {"query": ""}),
                             (api.sra_search, {"query": "ok", "limit": 0}),
                             (api.sra_run_metadata, {"run_accession": "GSM123"}),
                             (api.sra_studies, {"query": "a b\nc"}),
                             (api.sra_studies, {"query": "ok", "offset": -1})]:
            with patch.dict(os.environ, {"NCBI_EMAIL": "researcher@example.org"}), \
                 self.subTest(tool=func.__name__), self.assertRaises(ValueError):
                await func(**kwargs)
        with patch.dict(os.environ, {}, clear=True), self.assertRaises(ValueError):
            await api.sra_search("anything")

    async def test_api_error(self):
        with patch.dict(os.environ, {"NCBI_EMAIL": "researcher@example.org"}), \
             self.mock_http(lambda req: httpx.Response(404)), \
             patch("common.http.asyncio.sleep", new_callable=AsyncMock):
            with self.assertRaises(httpx.HTTPStatusError):
                await api.sra_search("human")
