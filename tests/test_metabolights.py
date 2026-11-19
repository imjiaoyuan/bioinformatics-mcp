"""Mocked tests for the MetaboLights MCP api."""
import httpx

from servers.metabolights_mcp import api
from tests.helpers import HTTPTestCase

CATALOGUE = {"content": ["MTBLS1", "MTBLS2", "MTBLS3"], "studies": []}
STUDY = {"mtblsStudy": {"mhdAccession": "MTBLS1", "studyStatus": "Public",
                        "datasetLicense": "CC-BY 4.0", "datasetLicenseUrl": "https://creativecommons.org",
                        "firstPublicDate": "2012-01-01", "studyFtpUrl": "ftp://example.org/MTBLS1",
                        "submitters": [{"email": "secret@example.org"}],
                        "studyHttpUrl": "https://example.org/MTBLS1", "revisionNumber": 2}}
FILES = {"latest": [], "obfuscationCode": "abc", "private": [], "study": [
    {"createdAt": "October 28 2026", "directory": "", "type": "metadata",
     "name": "i_Investigation.txt", "size": 12345, "sha256": "abc"}]}
ASSAYS = {"data": {"assays": ["a_MTBLS1_NMR_metabolite_profiling_NMR_spectroscopy.txt"]}, "errors": []}


class MetaboLightsTests(HTTPTestCase):
    async def test_catalogue_study_files_and_assays(self):
        seen = []

        def handler(req):
            seen.append(req.url.path)
            if req.url.path.endswith("/studies"):
                return httpx.Response(200, json=CATALOGUE)
            if req.url.path.endswith("/studies/MTBLS1"):
                return httpx.Response(200, json=STUDY)
            if req.url.path.endswith("/files"):
                return httpx.Response(200, json=FILES)
            if req.url.path.endswith("/assays"):
                return httpx.Response(200, json=ASSAYS)
            raise AssertionError(f"unexpected path: {req.url.path}")

        with self.mock_http(handler):
            catalogue = await api.metabolights_studies(limit=2)
            self.assertEqual(catalogue["results"], ["MTBLS1", "MTBLS2"])
            self.assertEqual(catalogue["total"], 3)
            self.assertTrue(catalogue["truncated"])
            study = await api.metabolights_study("mtbls1")
            self.assertEqual(study["datasetLicense"], "CC-BY 4.0")
            self.assertIn("submitters", STUDY["mtblsStudy"])
            self.assertNotIn("submitters", study)
            files = await api.metabolights_study_files("MTBLS1")
            self.assertEqual(files["results"][0]["name"], "i_Investigation.txt")
            self.assertEqual(files["accession"], "MTBLS1")
            assays = await api.metabolights_study_assays("MTBLS1")
            self.assertEqual(assays["total"], 1)
            self.assertIn("NMR_spectroscopy", assays["assays"][0])
        self.assertEqual(len(seen), 4)

    async def test_missing_study_is_an_error(self):
        with self.mock_http(lambda req: httpx.Response(200, json={})):
            with self.assertRaises(ValueError):
                await api.metabolights_study("MTBLS999999")

    async def test_validation_before_network(self):
        cases = [(api.metabolights_studies, {"limit": 0}),
                 (api.metabolights_studies, {"offset": -1}),
                 (api.metabolights_study, {"accession": "MTEX1"}),
                 (api.metabolights_study, {"accession": "mtbls"}),
                 (api.metabolights_study_files, {"accession": "MTBLS1", "limit": 0}),
                 (api.metabolights_study_files, {"accession": "ERR1"}),
                 (api.metabolights_study_assays, {"accession": "MTBLS1x"})]
        for func, kwargs in cases:
            with self.subTest(tool=func.__name__, kwargs=kwargs), self.assertRaises(ValueError):
                await func(**kwargs)

    async def test_api_error(self):
        with self.mock_http(lambda req: httpx.Response(500)):
            with self.assertRaises(httpx.HTTPStatusError):
                await api.metabolights_studies()
