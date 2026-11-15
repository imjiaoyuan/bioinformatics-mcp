from unittest.mock import AsyncMock, patch

import httpx

from servers.encode_mcp import api
from tests.helpers import HTTPTestCase


def _search_payload(hits, total):
    return {"@id": "/search/", "title": "Search", "total": total, "@graph": hits}


EXPERIMENT = {
    "@id": "/experiments/ENCSR000AEI/",
    "accession": "ENCSR000AEI",
    "status": "released",
    "assay_title": "RAMPAGE",
    "description": "Stranded PE101 RAMPAGE libraries.",
    "biosample_summary": "Homo sapiens GM12878",
    "biosample_ontology": {"term_name": "GM12878"},
    "bio_replicate_count": 2,
    "tech_replicate_count": 1,
    "replicates": [{"library": {"biosample": {"organism": {"scientific_name": "Homo sapiens"}}}}],
    "targets": [{"label": "TAF1"}],
    "controlled_by": ["/experiments/ENCSR000AED/"],
    "references": [{"identifier": "pmid:25742505"}],
    "files": [
        {"@id": "/files/ENCFF001SWU/", "accession": "ENCFF001SWU", "file_format": "fastq",
         "file_size": 5457169, "href": "/files/ENCFF001SWU/@@download/ENCFF001SWU.fastq.gz",
         "md5sum": "f1d0a2b0c1", "output_type": "reads", "status": "released"},
        {"@id": "/files/ENCFF001SXK/", "accession": "ENCFF001SXK", "file_format": "bigWig",
         "file_size": 17223752, "href": "/files/ENCFF001SXK/@@download/ENCFF001SXK.bigWig",
         "md5sum": None, "output_type": "signal of unique reads", "status": "released"},
    ],
}


def _search_handler(test, expected_type=None, hits=(), total=0):
    def handler(req):
        test.assertEqual(req.url.path, "/search/")
        if expected_type is not None:
            test.assertIn(("type", expected_type), req.url.params.items())
        return httpx.Response(200, json=_search_payload(list(hits), total))
    return handler


def _detail_handler(test):
    def handler(req):
        if req.url.path == "/experiments/ENCSR000AEI/":
            test.assertIn(("format", "json"), req.url.params.items())
            test.assertEqual(req.headers.get("Accept"), "application/json")
            return httpx.Response(200, json=EXPERIMENT)
        return httpx.Response(404)
    return handler


def _exp_hit(accession="ENCSR000AEI"):
    return {"@id": f"/experiments/{accession}/", "accession": accession,
            "assay_title": "total RNA-seq", "biosample_summary": "Homo sapiens GM12878",
            "status": "released"}


class EncodeTests(HTTPTestCase):
    async def test_search_success(self):
        def handler(req):
            items = req.url.params.items()
            self.assertIn(("type", "Experiment"), items)
            self.assertIn(("format", "json"), items)
            self.assertIn(("limit", "4"), items)  # offset+limit fetched, sliced locally
            self.assertIn(("status", "released"), items)
            self.assertIn(("assay_title", "total RNA-seq"), items)
            self.assertIn(("biosample_ontology.term_name", "GM12878"), items)
            self.assertIn(("target.label", "CTCF"), items)
            self.assertIn(("organism.scientific_name", "Homo sapiens"), items)
            self.assertEqual(req.headers.get("Accept"), "application/json")
            self.assertNotIn("start", req.url.params)
            return httpx.Response(200, json=_search_payload(
                [_exp_hit("ENCSR000AEI"), _exp_hit("ENCSR284QGB"), _exp_hit("ENCSR117BGR"),
                 _exp_hit("ENCSR999ZZZ"), _exp_hit("ENCSR888YYY")], 2249))
        with self.mock_http(handler), patch("common.http.asyncio.sleep", new_callable=AsyncMock):
            result = await api.encode_search(assay="total RNA-seq", biosample="GM12878",
                                             target="CTCF", organism="Homo sapiens",
                                             limit=3, offset=1)
        self.assertEqual(result["pagination"], "local")
        self.assertEqual(result["limit"], 3)
        self.assertEqual(result["offset"], 1)
        self.assertEqual(result["result_count"], 2249)
        self.assertEqual(len(result["results"]), 3)
        self.assertTrue(result["truncated"])
        first = result["results"][0]
        self.assertEqual(first["accession"], "ENCSR284QGB")
        self.assertEqual(first["url"], "https://www.encodeproject.org/experiments/ENCSR284QGB/")
        self.assertIn("source_url", result)

    async def test_search_requires_filters(self):
        with self.assertRaises(ValueError):
            await api.encode_search()

    async def test_experiment_detail(self):
        with self.mock_http(_detail_handler(self)), patch("common.http.asyncio.sleep", new_callable=AsyncMock):
            detail = await api.encode_experiment("encsr000aei")
        self.assertEqual(detail["accession"], "ENCSR000AEI")
        self.assertEqual(detail["assay_title"], "RAMPAGE")
        self.assertEqual(detail["biosample_summary"], "Homo sapiens GM12878")
        self.assertEqual(detail["organism"], "Homo sapiens")
        self.assertEqual(detail["targets"], ["TAF1"])
        self.assertEqual(detail["replicate_counts"], {"biological": 2, "technical": 1})
        self.assertEqual(detail["controlled_by"],
                         ["https://www.encodeproject.org/experiments/ENCSR000AED/"])
        self.assertEqual(detail["references"], ["pmid:25742505"])
        self.assertEqual(detail["file_counts"], {"bigWig": 1, "fastq": 1})
        self.assertEqual(detail["url"], "https://www.encodeproject.org/experiments/ENCSR000AEI/")

    async def test_files(self):
        with self.mock_http(_detail_handler(self)), patch("common.http.asyncio.sleep", new_callable=AsyncMock):
            files = await api.encode_files("ENCSR000AEI")
            self.assertEqual([row["accession"] for row in files["results"]],
                             ["ENCFF001SWU", "ENCFF001SXK"])
            row = files["results"][0]
            self.assertEqual(row["file_format"], "fastq")
            self.assertEqual(row["file_size"], 5457169)
            self.assertEqual(row["md5sum"], "f1d0a2b0c1")
            self.assertEqual(row["href"],
                             "https://www.encodeproject.org/files/ENCFF001SWU/@@download/ENCFF001SWU.fastq.gz")
            self.assertEqual(row["output_type"], "reads")
            bigwigs = await api.encode_files("ENCSR000AEI", file_type="BigWig", limit=5)
            self.assertEqual([r["accession"] for r in bigwigs["results"]], ["ENCFF001SXK"])
            self.assertEqual(bigwigs["file_type"], "BigWig")

    async def test_biosamples(self):
        hits = [{"@id": "/biosample-types/cell_line_EFO_0002784/", "term_name": "GM12878",
                 "classification": "cell line", "status": "released"}]
        with self.mock_http(_search_handler(self, "BiosampleType", hits, 1)), \
                patch("common.http.asyncio.sleep", new_callable=AsyncMock):
            result = await api.encode_biosamples("GM12878")
        self.assertEqual(result["results"][0]["term_name"], "GM12878")
        self.assertEqual(result["results"][0]["classification"], "cell line")
        self.assertEqual(result["results"][0]["url"],
                         "https://www.encodeproject.org/biosample-types/cell_line_EFO_0002784/")
        self.assertEqual(result["result_count"], 1)

    async def test_target(self):
        hits = [{"@id": "/targets/CTCF-human/", "label": "CTCF",
                 "organism": {"scientific_name": "Homo sapiens"},
                 "investigated_as": ["transcription factor"], "status": "released"},
                {"@id": "/targets/CTCF-mouse/", "label": "CTCF",
                 "organism": {"scientific_name": "Mus musculus"},
                 "investigated_as": ["transcription factor"], "status": "released"}]
        with self.mock_http(_search_handler(self, "Target", hits, 3)), \
                patch("common.http.asyncio.sleep", new_callable=AsyncMock):
            result = await api.encode_target("CTCF")
        self.assertEqual(result["total"], 3)
        self.assertEqual([row["organism"] for row in result["results"]],
                         ["Homo sapiens", "Mus musculus"])
        self.assertEqual(result["results"][0]["url"],
                         "https://www.encodeproject.org/targets/CTCF-human/")

    async def test_validation_errors(self):
        with self.mock_http(_detail_handler(self)), patch("common.http.asyncio.sleep", new_callable=AsyncMock):
            cases = [
                (api.encode_experiment, {"accession": "ENCSR00"}),
                (api.encode_experiment, {"accession": "ENCSR000AE"}),
                (api.encode_experiment, {"accession": "ENCSR000AEIX"}),
                (api.encode_experiment, {"accession": ""}),
                (api.encode_files, {"accession": "ENCFF000AAA"}),
                (api.encode_search, {"assay": "x", "status": "draft"}),
                (api.encode_search, {"assay": "x", "limit": 0}),
                (api.encode_search, {"assay": "x", "offset": 501, "limit": 500}),
                (api.encode_search, {"query": "x", "offset": -1}),
                (api.encode_biosamples, {"term": ""}),
                (api.encode_target, {"label": "CT CTF"}),
                (api.encode_target, {"label": "CTCF!"}),
                (api.encode_files, {"accession": "ENCSR000AEI", "file_type": ""}),
            ]
            for func, kwargs in cases:
                with self.subTest(tool=func.__name__, kwargs=kwargs), self.assertRaises(ValueError):
                    await func(**kwargs)

    async def test_offset_cap(self):
        with self.assertRaises(ValueError):
            await api.encode_search(assay="RNA-seq", limit=20, offset=600)

    async def test_api_404(self):
        with self.mock_http(lambda req: httpx.Response(404)), \
                patch("common.http.asyncio.sleep", new_callable=AsyncMock):
            with self.assertRaises(httpx.HTTPStatusError):
                await api.encode_experiment("ENCSR000AEI")

    async def test_oversized_response(self):
        def handler(req):
            self.assertEqual(req.url.path, "/experiments/ENCSR000AEI/")
            return httpx.Response(200, content=b"x" * (api.DETAIL_MAX_BYTES + 1))
        with self.mock_http(handler), patch("common.http.asyncio.sleep", new_callable=AsyncMock):
            with self.assertRaises(ValueError):
                await api.encode_experiment("ENCSR000AEI")
