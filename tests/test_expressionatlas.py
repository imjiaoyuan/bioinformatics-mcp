import asyncio
from unittest.mock import AsyncMock, patch

import httpx

from servers.expressionatlas_mcp import api
from tests.helpers import HTTPTestCase


def _catalogue():
    return {"experiments": [
        {"experimentAccession": "E-MTAB-2836",
         "experimentDescription": "RNA-seq of human tissues",
         "species": "Homo sapiens",
         "kingdom": "animals",
         "loadDate": "04-02-2016",
         "lastUpdate": "04-02-2016",
         "rawExperimentType": "RNASEQ_MRNA_BASELINE",
         "technologyType": ["RNA-Seq mRNA"],
         "numberOfAssays": 122,
         "experimentalFactors": ["organism part"],
         "experimentProjects": []},
        {"experimentAccession": "E-MTAB-4045",
         "experimentDescription": "Soybean seeds RNA-seq",
         "species": "Glycine max",
         "kingdom": "plants",
         "rawExperimentType": "RNASEQ_MRNA_BASELINE",
         "technologyType": ["RNA-Seq mRNA"],
         "numberOfAssays": 273,
         "experimentalFactors": ["developmental stage", "organism part"],
         "experimentProjects": []},
        {"experimentAccession": "E-GEOD-21860",
         "experimentDescription": "Breast cancer microarray",
         "species": "Homo sapiens",
         "kingdom": "animals",
         "rawExperimentType": "MICROARRAY_1COLOR_MRNA_DIFFERENTIAL",
         "technologyType": ["Microarray 1-colour mRNA"],
         "numberOfAssays": 46,
         "experimentalFactors": ["disease"],
         "arrayDesigns": ["A-AFFY-44"],
         "arrayDesignNames": ["Affymetrix GeneChip Human Genome U133 Plus 2.0"],
         "experimentProjects": []},
        {"experimentAccession": "E-PROT-7",
         "experimentDescription": "Proteomics of plasma",
         "species": "Oryza sativa",
         "kingdom": "plants",
         "rawExperimentType": "PROTEOMICS_BASELINE",
         "technologyType": ["Proteomics"],
         "numberOfAssays": 12,
         "experimentalFactors": ["tissue"],
         "experimentProjects": []},
    ]}


def _detail():
    return {
        "experiment": {"accession": "E-MTAB-2836", "type": "rnaseq_mrna_baseline",
                       "description": "RNA-seq of coding RNA from 122 human individuals",
                       "species": "Homo sapiens", "urls": {}},
        "config": {"species": "Homo sapiens", "disclaimer": ""},
        "columnHeaders": [
            {"assayGroupId": "g1", "factorValue": "adipose tissue",
             "factorValueOntologyTermId": "UBERON_0001013",
             "assayGroupSummary": {"replicates": 3, "properties": [
                 {"propertyName": "organism part", "testValue": "adipose tissue",
                  "contrastPropertyType": "FACTOR"},
                 {"propertyName": "organism", "testValue": "Homo sapiens",
                  "contrastPropertyType": "SAMPLE"}]}},
            {"assayGroupId": "g2", "factorValue": "adrenal gland",
             "factorValueOntologyTermId": "UBERON_0002369",
             "assayGroupSummary": {"replicates": 3, "properties": [
                 {"propertyName": "organism part", "testValue": "adrenal gland",
                  "contrastPropertyType": "FACTOR"}]}},
        ],
        "columnGroupings": [],
        "profiles": {},
        "anatomogram": {"species": "Homo sapiens"},
    }


class ExpressionAtlasTests(HTTPTestCase):
    def setUp(self):
        super().setUp()
        api._reset_cache()
        api._lock = asyncio.Lock()

    def _handler(self, calls):
        def handler(req):
            calls.append((req.url.path, dict(req.url.params)))
            if req.url.path == "/gxa/json/experiments":
                return httpx.Response(200, json=_catalogue())
            if req.url.path == "/gxa/json/experiments/E-MTAB-2836":
                return httpx.Response(200, json=_detail())
            return httpx.Response(404)
        return handler

    async def test_experiments_filtering_and_pagination(self):
        calls = []
        with self.mock_http(self._handler(calls)), \
                patch("common.http.asyncio.sleep", new_callable=AsyncMock):
            page = await api.atlas_experiments(species="homo_sapiens", limit=1, offset=0)
            self.assertEqual(calls, [("/gxa/json/experiments", {})])
            self.assertEqual(page["pagination"], "local")
            self.assertEqual(page["total"], 2)
            self.assertEqual([row["experiment_accession"] for row in page["results"]],
                             ["E-MTAB-2836"])
            self.assertTrue(page["truncated"])
            self.assertEqual(page["source_url"], "https://www.ebi.ac.uk/gxa/json/experiments")
            second = await api.atlas_experiments(species="homo_sapiens", limit=1, offset=1)
            self.assertEqual([row["experiment_accession"] for row in second["results"]],
                             ["E-GEOD-21860"])
            self.assertFalse(second["truncated"])
            self.assertEqual(len(calls), 1, "catalogue must be fetched once per process")
            microarray = await api.atlas_experiments(assay="microarray")
            self.assertEqual(microarray["total"], 1)
            self.assertEqual(microarray["results"][0]["array_design_names"],
                             ["Affymetrix GeneChip Human Genome U133 Plus 2.0"])
            proteomics = await api.atlas_experiments(assay="proteomics")
            self.assertEqual(proteomics["results"][0]["experiment_accession"], "E-PROT-7")
            hits = await api.atlas_experiments(query="soybean")
            self.assertEqual(hits["total"], 1)
            self.assertEqual(hits["results"][0]["species"], "Glycine max")
            everything = await api.atlas_experiments(limit=10)
            self.assertEqual(everything["total"], 4)

    async def test_experiment_detail(self):
        calls = []
        with self.mock_http(self._handler(calls)), \
                patch("common.http.asyncio.sleep", new_callable=AsyncMock):
            detail = await api.atlas_experiment("e-mtab-2836")
            self.assertEqual([path for path, _ in calls],
                             ["/gxa/json/experiments/E-MTAB-2836", "/gxa/json/experiments"])
            self.assertEqual(detail["experiment_accession"], "E-MTAB-2836")
            self.assertEqual(detail["species"], "Homo sapiens")
            self.assertEqual(detail["experiment_type"], "rnaseq_mrna_baseline")
            self.assertEqual(detail["number_of_assay_groups"], 2)
            self.assertEqual(detail["total_replicates"], 6)
            self.assertEqual(detail["number_of_assays"], 122)
            self.assertEqual(detail["factors"],
                             [{"factor": "organism part", "value": "adipose tissue"},
                              {"factor": "organism part", "value": "adrenal gland"}])
            self.assertEqual(detail["assay_groups"][0]["replicates"], 3)
            self.assertIn("E-MTAB-2836", detail["web_url"])

    async def test_cache_shared_between_tools(self):
        calls = []
        with self.mock_http(self._handler(calls)), \
                patch("common.http.asyncio.sleep", new_callable=AsyncMock):
            await api.atlas_experiments()
            calls.clear()
            detail = await api.atlas_experiment("E-MTAB-2836")
            self.assertEqual([path for path, _ in calls],
                             ["/gxa/json/experiments/E-MTAB-2836"])
            self.assertEqual(detail["array_designs"], [])

    async def test_validation_before_network(self):
        calls = []
        with self.mock_http(self._handler(calls)), \
                patch("common.http.asyncio.sleep", new_callable=AsyncMock):
            for func, args in [
                (api.atlas_experiments, {"species": ""}),
                (api.atlas_experiments, {"assay": "x" * 101}),
                (api.atlas_experiments, {"query": "ok", "limit": 0}),
                (api.atlas_experiments, {"query": "ok", "offset": -1}),
                (api.atlas_experiments, {"query": "ok", "limit": 101}),
                (api.atlas_experiment, {"accession": "EMTAB-2836"}),
                (api.atlas_experiment, {"accession": "E-1234-12"}),
                (api.atlas_experiment, {"accession": "E-XXXX-00000000A"}),
            ]:
                with self.subTest(tool=func.__name__, args=args), self.assertRaises(ValueError):
                    await func(**args)
            self.assertEqual(calls, [], "invalid input must not trigger any request")

    async def test_unknown_accession_404(self):
        def handler(req):
            return httpx.Response(404)
        with self.mock_http(handler), patch("common.http.asyncio.sleep", new_callable=AsyncMock):
            with self.assertRaises(httpx.HTTPStatusError):
                await api.atlas_experiment("E-MTAB-9999")
