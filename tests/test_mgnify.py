"""Mocked tests for the MGnify MCP api."""
import httpx

from servers.mgnify_mcp import api
from tests.helpers import HTTPTestCase

STUDIES = {"data": [
    {"type": "studies", "id": "MGYS00006862",
     "attributes": {"accession": "MGYS00006862", "study-name": "Ocean microbiome",
                    "study-abstract": "Marine sampling", "samples-count": 100,
                    "centre-name": "EMBL", "bioproject": "PRJEB92327"}}],
    "meta": {"pagination": {"count": 84, "page": 2, "pages": 5}}}
STUDY = {"data": {"type": "studies", "id": "MGYS00006862",
                  "attributes": {"accession": "MGYS00006862", "study-name": "Ocean microbiome",
                                 "study-abstract": "Marine sampling", "samples-count": 100,
                                 "centre-name": "EMBL", "bioproject": "PRJEB92327"}}}
ANALYSES = {"data": [{"type": "analyses", "id": "MGYA00000001",
                      "attributes": {"accession": "MGYA00000001", "analysis-status": "completed",
                                     "experiment-type": "metagenomics", "instrument-platform": "ILLUMINA",
                                     "instrument-model": "NovaSeq 6000", "pipeline-version": "5.1",
                                     "complete-time": "2025-01-01"}}],
            "meta": {"pagination": {"count": 84, "page": 1, "pages": 84}}}
BIOME = {"data": {"type": "biomes", "id": "root:Environmental:Air",
                  "attributes": {"samples-count": 160, "biome-name": "Air",
                                 "lineage": "root:Environmental:Air"}}}


class MgnifyTests(HTTPTestCase):
    async def test_studies_study_analyses_and_biome(self):
        seen = []

        def handler(req):
            seen.append((req.url.path, dict(req.url.params)))
            if req.url.path.endswith("/studies"):
                self.assertEqual(req.url.params["lineage"], "root:Environmental:Air")
                self.assertEqual(req.url.params["page"], "2")
                self.assertEqual(req.url.params["page_size"], "1")
                return httpx.Response(200, json=STUDIES)
            if req.url.path.endswith("/studies/MGYS00006862"):
                return httpx.Response(200, json=STUDY)
            if req.url.path.endswith("/analyses"):
                self.assertEqual(req.url.params["study_accession"], "MGYS00006862")
                return httpx.Response(200, json=ANALYSES)
            if "/biomes/" in req.url.path:
                return httpx.Response(200, json=BIOME)
            raise AssertionError(f"unexpected path: {req.url.path}")

        with self.mock_http(handler):
            studies = await api.mgnify_studies(lineage="root:Environmental:Air", page_index=2, page_size=1)
            self.assertEqual(studies["results"][0]["accession"], "MGYS00006862")
            self.assertEqual(studies["count"], 84)
            self.assertEqual(studies["pages"], 5)
            study = await api.mgnify_study("mgys00006862")
            self.assertEqual(study["name"], "Ocean microbiome")
            analyses = await api.mgnify_analyses("MGYS00006862", page_size=1)
            self.assertEqual(analyses["results"][0]["pipeline_version"], "5.1")
            self.assertEqual(analyses["pages"], 84)
            biome = await api.mgnify_biome("root:Environmental:Air")
            self.assertEqual(biome["samples_count"], 160)
        self.assertEqual(len(seen), 4)

    async def test_not_found_is_an_error(self):
        with self.mock_http(lambda req: httpx.Response(200, json={"errors": [{"detail": "Not found."}]})):
            with self.assertRaises(ValueError):
                await api.mgnify_study("MGYS99999999")

    async def test_validation_before_network(self):
        cases = [(api.mgnify_studies, {"lineage": "root;Environmental"}),
                 (api.mgnify_studies, {"lineage": "root", "page_index": 0}),
                 (api.mgnify_studies, {"lineage": "root", "page_size": 101}),
                 (api.mgnify_study, {"accession": "SRR1"}),
                 (api.mgnify_analyses, {"study_accession": "ERR123"}),
                 (api.mgnify_analyses, {"study_accession": "MGYS00006862", "page_size": 0}),
                 (api.mgnify_biome, {"lineage": "soil"})]
        for func, kwargs in cases:
            with self.subTest(tool=func.__name__, kwargs=kwargs), self.assertRaises(ValueError):
                await func(**kwargs)

    async def test_api_error(self):
        with self.mock_http(lambda req: httpx.Response(503)):
            with self.assertRaises(httpx.HTTPStatusError):
                await api.mgnify_biome("root:Environmental:Air")
