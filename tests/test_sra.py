import os
from unittest.mock import AsyncMock, patch

import httpx

from servers.sra_mcp import server
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
            search = await server.sra_search('organism="Homo sapiens"', limit=5, offset=1)
            self.assertEqual(search["count"], 2)
            self.assertEqual(search["uids"], ["8", "9"])
            self.assertIn("source_url", search)
            metadata = await server.sra_run_metadata("srr000001")
            self.assertEqual(metadata["study"][0]["acc"], "SRP000001")
            self.assertEqual(metadata["organism"][0]["ScientificName"], "Homo sapiens")
            self.assertEqual(metadata["runs"][0]["acc"], "SRR000001")
            self.assertIn("source_url", metadata)
            studies = await server.sra_studies("human", limit=5)
            self.assertEqual(studies["count"], 2)
            self.assertEqual(len(studies["results"]), 1)
            self.assertEqual(studies["results"][0]["study_accession"], "SRP000001")
            self.assertEqual(studies["results"][0]["organisms"], ["Homo sapiens"])
            self.assertIn("source_url", studies)

    async def test_validation_all_tools(self):
        for func, kwargs in [(server.sra_search, {"query": ""}),
                             (server.sra_search, {"query": "ok", "limit": 0}),
                             (server.sra_run_metadata, {"run_accession": "GSM123"}),
                             (server.sra_studies, {"query": "a b\nc"}),
                             (server.sra_studies, {"query": "ok", "offset": -1})]:
            with patch.dict(os.environ, {"NCBI_EMAIL": "researcher@example.org"}), \
                 self.subTest(tool=func.__name__), self.assertRaises(ValueError):
                await func(**kwargs)
        with patch.dict(os.environ, {}, clear=True), self.assertRaises(ValueError):
            await server.sra_search("anything")

    async def test_api_error(self):
        with patch.dict(os.environ, {"NCBI_EMAIL": "researcher@example.org"}), \
             self.mock_http(lambda req: httpx.Response(404)), \
             patch("common.http.asyncio.sleep", new_callable=AsyncMock):
            with self.assertRaises(httpx.HTTPStatusError):
                await server.sra_search("human")
