import unittest
from unittest.mock import AsyncMock, patch

import httpx

from servers.hgnc_mcp import api
from tests.helpers import HTTPTestCase


def _braf_response(**overrides):
    doc = {
        "hgnc_id": "HGNC:1097",
        "symbol": "BRAF",
        "name": "B-Raf proto-oncogene, serine/threonine kinase",
        "status": "Approved",
        "locus_group": "protein-coding gene",
        "locus_type": "gene with protein product",
        "location": "7q34",
        "alias_symbol": ["BRAF1", "BRAF-1"],
        "prev_name": ["v-raf murine sarcoma viral oncogene homolog B"],
        "ensembl_gene_id": "ENSG00000157764",
        "entrez_id": "673",
        "uniprot_ids": ["P15056"],
        "vega_id": "OTTHUMG00000157457",
        "refseq_accession": ["NM_004333"],
        "date_approved_reserved": "1991-07-16T00:00:00Z",
        "date_modified": "2023-01-20T00:00:00Z",
    }
    doc.update(overrides)
    return {"responseHeader": {"status": 0}, "response": {"numFound": 1, "start": 0, "docs": [doc]}}


def _search_response(docs, num_found=None):
    return {"responseHeader": {"status": 0},
            "response": {"numFound": num_found if num_found is not None else len(docs),
                         "start": 0, "docs": docs}}


class HgncTests(HTTPTestCase):
    async def _call(self, handler, func, **kwargs):
        with self.mock_http(handler), patch("common.http.asyncio.sleep", new_callable=AsyncMock):
            return await func(**kwargs)

    async def test_entry_accept_header_and_success(self):
        checks = {}

        def handler(request):
            checks["accept"] = request.headers.get("accept")
            checks["url"] = str(request.url)
            return httpx.Response(200, json=_braf_response())

        entry = await self._call(handler, api.hgnc_entry, hgnc_id="HGNC:1097")
        self.assertEqual(checks["accept"], "application/json")
        self.assertEqual(checks["url"], "https://rest.genenames.org/fetch/hgnc_id/HGNC:1097")
        self.assertEqual(entry["symbol"], "BRAF")
        self.assertEqual(entry["status"], "Approved")
        self.assertEqual(entry["uniprot_ids"], ["P15056"])
        self.assertEqual(entry["ensembl_gene_id"], "ENSG00000157764")
        self.assertEqual(entry["date_modified"], "2023-01-20T00:00:00Z")
        self.assertIn("rest.genenames.org", entry["source_url"])

    async def test_symbol_success(self):
        def handler(request):
            self.assertEqual(request.headers.get("accept"), "application/json")
            self.assertEqual(request.url.raw_path, b"/fetch/symbol/TP53")
            return httpx.Response(200, json=_braf_response(symbol="TP53", hgnc_id="HGNC:11998"))

        entry = await self._call(handler, api.hgnc_symbol, symbol="TP53")
        self.assertEqual(entry["hgnc_id"], "HGNC:11998")
        self.assertEqual(entry["symbol"], "TP53")

    async def test_missing_symbol_404(self):
        with self.assertRaises(httpx.HTTPStatusError):
            await self._call(lambda req: httpx.Response(404), api.hgnc_symbol, symbol="NOPEXYZ")

    async def test_search_pagination_and_lucene(self):
        checks = {}

        def handler(request):
            checks["path"] = request.url.path
            docs = [{"hgnc_id": f"HGNC:{1000 + index}", "symbol": f"TP53X{index}"}
                    for index in range(40)]
            return httpx.Response(200, json=_search_response(docs, num_found=45387))

        result = await self._call(handler, api.hgnc_search,
                                  query="status:Approved AND symbol:TP53*", limit=5, offset=10)
        self.assertEqual(checks["path"], "/search/status:Approved AND symbol:TP53*")
        self.assertEqual(result["total"], 45387)
        self.assertEqual(result["limit"], 5)
        self.assertEqual(result["offset"], 10)
        self.assertEqual([row["symbol"] for row in result["results"]],
                         ["TP53X10", "TP53X11", "TP53X12", "TP53X13", "TP53X14"])
        self.assertIn("local", result["pagination"])
        self.assertIn("rest.genenames.org", result["source_url"])

    async def test_search_escapes_lucene_characters(self):
        def handler(request):
            return httpx.Response(200, json=_search_response([]))

        with self.assertRaises(ValueError) as ctx:
            await self._call(handler, api.hgnc_search, query='status:Approved AND name:"B-raf (kinase)"%23')
        self.assertIn("must not contain", str(ctx.exception))
        with self.assertRaises(ValueError):
            await self._call(handler, api.hgnc_search, query='status:Approved\\ AND')

    async def test_aliases(self):
        def handler(request):
            self.assertEqual(request.url.path, "/fetch/symbol/BRAF")
            return httpx.Response(200, json=_braf_response(
                alias_name=["B-Raf", "BRAF1"], prev_symbol=["BRAF"]))

        result = await self._call(handler, api.hgnc_aliases, symbol="BRAF")
        self.assertEqual(result["total"], 5)
        self.assertEqual(result["results"], ["B-Raf", "BRAF", "BRAF-1", "BRAF1",
                                             "v-raf murine sarcoma viral oncogene homolog B"])
        self.assertEqual(result["hgnc_id"], "HGNC:1097")
        paged = await self._call(handler, api.hgnc_aliases, symbol="BRAF", limit=2, offset=2)
        self.assertEqual(paged["results"], ["BRAF-1", "BRAF1"])

    async def test_validation_all_tools(self):
        handler = lambda req: httpx.Response(200, json=_braf_response())
        cases = [(api.hgnc_entry, {"hgnc_id": "BRAF"}),
                 (api.hgnc_entry, {"hgnc_id": "HGNC:abc"}),
                 (api.hgnc_entry, {"hgnc_id": "1097; drop"}),
                 (api.hgnc_entry, {"hgnc_id": ""}),
                 (api.hgnc_symbol, {"symbol": "TP53;"}),
                 (api.hgnc_symbol, {"symbol": "x" * 31}),
                 (api.hgnc_search, {"query": ""}),
                 (api.hgnc_search, {"query": "TP53", "limit": 0}),
                 (api.hgnc_search, {"query": "TP53", "limit": 101}),
                 (api.hgnc_search, {"query": "TP53", "offset": -1}),
                 (api.hgnc_aliases, {"symbol": "TP53!", "limit": 1, "offset": 0})]
        for func, kwargs in cases:
            with self.subTest(tool=func.__name__, kwargs=kwargs), \
                    self.mock_http(handler), \
                    patch("common.http.asyncio.sleep", new_callable=AsyncMock), \
                    self.assertRaises(ValueError):
                await func(**kwargs)

    async def test_unknown_entry_raises_clear_error(self):
        body = {"responseHeader": {"status": 0}, "response": {"numFound": 0, "start": 0, "docs": []}}
        with self.assertRaises(ValueError) as ctx:
            await self._call(lambda req: httpx.Response(200, json=body),
                             api.hgnc_symbol, symbol="NOPEXYZ")
        self.assertIn("No matching HGNC entry", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
