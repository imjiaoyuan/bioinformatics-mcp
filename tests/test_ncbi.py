from unittest.mock import AsyncMock, patch

import httpx
import json

from servers.ncbi_mcp import server
from tests.helpers import HTTPTestCase


class GEOTests(HTTPTestCase):
    async def test_search_summaries(self):
        with patch.object(server, "ncbi_search", AsyncMock(return_value={"ids": ["1"]})) as search, \
             patch.object(server, "ncbi_summary", AsyncMock(return_value={"result": {"1": {"accession": "GSE1"}}})):
            result = await server.geo_search("rice", 2)
            search.assert_awaited_once_with("gds", "rice", 2)
            self.assertEqual(result["summaries"]["1"]["accession"], "GSE1")

    async def test_search_filters_build_entrez_query(self):
        with patch.object(server, "ncbi_search", AsyncMock(return_value={"ids": []})) as search:
            result = await server.geo_search(organism="human", data_type="long_reads")
            term = result["query"]
            search.assert_awaited_once_with("gds", term, 20)
            self.assertIn('"Homo sapiens"[Organism]', term)
            self.assertIn("long read", term)

    async def test_search_entry_type_and_topic(self):
        with patch.object(server, "ncbi_search", AsyncMock(return_value={"ids": []})) as search:
            result = await server.geo_search(query="heat stress", organism="arabidopsis",
                                             data_type="scrna", entry_type="series")
            term = result["query"]
            self.assertIn('"heat stress"', term)
            self.assertIn('"Arabidopsis thaliana"[Organism]', term)
            self.assertIn("single cell", term)
            self.assertIn("gse[ETYP]", term)

    async def test_sra_search_exact_fields(self):
        async def search(database, query, max_results=20):
            if database == "taxonomy":
                return {"ids": ["9606"]}
            return {"ids": ["1"], "query": query, "count": 1}
        with patch.object(server, "ncbi_search", side_effect=search) as search, \
             patch.object(server, "ncbi_summary", AsyncMock(return_value={"result": {}})):
            result = await server.sra_search(organism="human", strategy="wgs",
                                             platform="pacbio", query="brain")
            term = result["query"]
            search.assert_any_await("sra", term, 20)
            self.assertIn("txid9606[Organism]", term)
            self.assertIn("WGS[Strategy]", term)
            self.assertIn("PACBIO_SMRT[Platform]", term)
            self.assertIn("brain", term)

    async def test_sra_search_validation(self):
        with self.assertRaises(ValueError):
            await server.sra_search()
        with self.assertRaises(ValueError):
            await server.sra_search(strategy="magic")
        with self.assertRaises(ValueError):
            await server.sra_search(organism="no-such-organism-xyz", strategy="wgs")

    async def test_find_data_routes_geo_and_sra(self):
        async def search(database, query, max_results=20):
            if database == "taxonomy":
                return {"ids": ["3702"]}
            return {"ids": ["100"], "query": query, "count": 5}
        with patch.object(server, "ncbi_search", side_effect=search) as search, \
             patch.object(server, "ncbi_summary", AsyncMock(return_value={"result": {}})):
            result = await server.find_data(organism="arabidopsis", data_type="scrna",
                                            condition="heat", archives="geo,sra")
            self.assertEqual(result["organism"], "arabidopsis")
            geo_term = result["geo"]["query"]
            sra_term = result["sra"]["query"]
            self.assertIn('"Arabidopsis thaliana"[Organism]', geo_term)
            self.assertIn("single cell", geo_term)
            self.assertIn("txid3702[Organism]", sra_term)
            self.assertIn("RNA-Seq[Strategy]", sra_term)
            self.assertIn("heat", geo_term)
            self.assertEqual(result["geo"]["count"], 5)
            self.assertEqual(result["sra"]["count"], 5)

    async def test_find_data_validation(self):
        with self.assertRaises(ValueError):
            await server.find_data()
        with self.assertRaises(ValueError):
            await server.find_data(data_type="metabolomics")
        with self.assertRaises(ValueError):
            await server.find_data(condition="drought", entry_type="study")

    async def test_sra_files_expand_runs(self):
        # NCBI runinfo CSV ships without a header row; the tool must inject one.
        rows = ("SRR1,2026-01-01,2026-01-01,1000,90000,0,90,1.5,,"
                "ftp://sra-download.ncbi.nlm.nih.gov/traces/SRR/000001/SRR1,"
                "SRX1,name,WGS,RANDOM,GENOMIC,SINGLE,0,0,PACBIO_SMRT,Sequel II,"
                "SRP1,PRJNA1,,123,SAMN1,SAMD1,simple,9606,Homo sapiens,sample,,,,\n"
                "SRR2,2026-01-01,2026-01-01,2000,180000,0,90,3.0,,"
                "https://sra-download.ncbi.nlm.nih.gov/traces/SRR/000002/SRR2,"
                "SRX1,name,WGS,RANDOM,GENOMIC,SINGLE,0,0,PACBIO_SMRT,Sequel II,"
                "SRP1,PRJNA1,,123,SAMN1,SAMD1,simple,9606,Homo sapiens,sample,,,,\n")

        def handler(req):
            self.assertIn("efetch.fcgi", req.url.path)
            self.assertEqual(req.url.params["db"], "sra")
            self.assertEqual(req.url.params["rettype"], "runinfo")
            self.assertIn("100", req.url.params["id"])
            return httpx.Response(200, text=rows)

        async def search(database, query, max_results=20):
            assert database == "sra" and "SRP1[Accession]" in query
            return {"ids": ["100"], "query": query, "count": 1}

        with self.mock_http(handler), patch.object(server, "ncbi_search", side_effect=search):
            result = await server.sra_files(["srp1"], limit=1)
        self.assertEqual(result["returned"], 1)
        run = result["runs"][0]
        self.assertEqual(run["run"], "SRR1")
        self.assertEqual(run["platform"], "PACBIO_SMRT")
        self.assertEqual(run["strategy"], "WGS")
        self.assertEqual(run["spots"], 1000)
        self.assertTrue(run["download_url"].startswith("https://"))

    async def test_sra_files_validation(self):
        with self.assertRaises(ValueError):
            await server.sra_files([])
        with self.assertRaises(ValueError):
            await server.sra_files(["SRR1", "SRR2", "SRR3", "SRR4", "SRR5", "SRR6",
                                    "SRR7", "SRR8", "SRR9", "SRR10", "SRR11", "SRR12",
                                    "SRR13", "SRR14", "SRR15", "SRR16", "SRR17", "SRR18",
                                    "SRR19", "SRR20", "SRR21"])
        with self.assertRaises(ValueError):
            await server.sra_files(["../../etc"])

    async def test_find_data_four_archives(self):
        async def search(database, query, max_results=20):
            if database == "taxonomy":
                return {"ids": ["4530"]}
            return {"ids": ["100"], "query": query, "count": 7}

        ena_rows = [{"run_accession": "DRR1", "study_accession": "PRJDB1",
                     "study_title": "rice RNA-seq", "scientific_name": "Oryza sativa",
                     "library_strategy": "RNA-Seq", "instrument_platform": "ILLUMINA",
                     "fastq_bytes": "100;200"}]
        gsa_rows = [{"id": "CRA1", "type": "GSA", "title": "rice study",
                     "url": "https://ngdc.cncb.ac.cn/gsa/browse/CRA1", "dbId": "gsa"}]

        def handler(req):
            if "ebi.ac.uk" in req.url.host:
                self.assertIn("tax_eq(4530)", req.url.params["query"])
                return httpx.Response(200, text=json.dumps(ena_rows))
            self.assertIn("ngdc.cncb.ac.cn", req.url.host)
            return httpx.Response(200, text=json.dumps(
                {"result": {"data": {"recordsFiltered": 1, "data": gsa_rows}}}))

        with self.mock_http(handler), patch.object(server, "ncbi_search", side_effect=search), \
             patch.object(server, "ncbi_summary", AsyncMock(return_value={"result": {}})):
            result = await server.find_data(organism="rice", data_type="rna_seq",
                                            condition="drought", archives="geo,sra,ena,gsa")
        self.assertEqual(result["ena"]["runs"][0]["run"], "DRR1")
        self.assertEqual(result["ena"]["runs"][0]["fastq_bytes"], 300)
        self.assertEqual(result["gsa"]["records"][0]["id"], "CRA1")
        self.assertEqual(result["geo"]["count"], 7)
        self.assertIn("txid4530[Organism]", result["sra"]["query"])

    async def test_find_data_archives_validation(self):
        with self.assertRaises(ValueError):
            await server.find_data(condition="x", archives="geo,ncbi")
        with self.assertRaises(ValueError):
            await server.find_data(condition="x", archives="")

    async def test_download_plan_mixed_sources(self):
        ena_like = None
        rows = ("SRR1,2026-01-01,2026-01-01,1000,90000,0,90,150.5,,"
                "https://sra-download.ncbi.nlm.nih.gov/traces/SRR/000001/SRR1,"
                "SRX1,name,WGS,RANDOM,GENOMIC,SINGLE,0,0,PACBIO_SMRT,Sequel II,"
                "SRP1,PRJNA1,,123,SAMN1,SAMD1,simple,9606,Homo sapiens,sample,,,,\n")

        async def search(database, query, max_results=20):
            if database == "taxonomy":
                return {"ids": ["1"]}
            return {"ids": ["9"], "query": query, "count": 1}

        def geo_handler(req):
            if "/suppl/" in req.url.path:
                return httpx.Response(404, text="")
            return httpx.Response(200, text='<a href="../">up</a><a href="GSE1_series_matrix.txt.gz">m</a>')

        def sra_handler(req):
            return httpx.Response(200, text=rows)

        def router(req):
            return geo_handler(req) if "ftp.ncbi.nlm.nih.gov" in req.url.host else sra_handler(req)

        with self.mock_http(router), patch.object(server, "ncbi_search", side_effect=search), \
             patch.object(server, "ncbi_summary", AsyncMock(return_value={"result": {}})):
            plan = await server.download_plan(["GSE1", "SRP1"])
        self.assertEqual(plan["count"], 2)
        self.assertEqual(plan["items"][0]["source"], "geo")
        self.assertEqual(plan["items"][1]["source"], "sra")
        self.assertEqual(plan["total_known_size_mb"], 150.5)
        self.assertIn("aria2_input", plan)
        self.assertIn("wget -c", plan["wget_script"])
        self.assertNotIn(ena_like, plan["items"])

    async def test_geo_metadata_rows_and_csv(self):
        soft = (
            "!Sample_geo_accession = GSM1\n!Sample_title = leaf A\n"
            "!Sample_source_name_ch1 = leaf\n!Sample_organism_ch1 = Arabidopsis thaliana\n"
            "!Sample_molecule_ch1 = total RNA\n!Sample_characteristics_ch1 = treatment: heat\n"
            "!Sample_geo_accession = GSM2\n!Sample_title = leaf B\n"
            "!Sample_source_name_ch1 = leaf\n!Sample_organism_ch1 = Arabidopsis thaliana\n"
            "!Sample_molecule_ch1 = total RNA\n!Sample_characteristics_ch1 = treatment: cold\n"
        )

        def handler(req):
            self.assertEqual(req.url.params["targ"], "gsm")
            return httpx.Response(200, text=soft)

        with self.mock_http(handler):
            result = await server.geo_metadata(["GSE1"])
        self.assertEqual(result["samples"], 2)
        self.assertEqual(result["rows"][0]["sample"], "GSM1")
        self.assertIn("treatment: heat", result["rows"][0]["characteristics"])
        self.assertIn("series,sample,title", result["csv"].splitlines()[0])
        self.assertIn("treatment:cold", result["csv"].replace(" ", "").replace('"', ""))

    async def test_geo_metadata_validation(self):
        with self.assertRaises(ValueError):
            await server.geo_metadata([])
        with self.assertRaises(ValueError):
            await server.geo_metadata(["../../etc"])

    async def test_record_characteristics(self):
        with self.mock_http(lambda req: httpx.Response(200, text="!Sample_characteristics_ch1 = treatment: heat\n!Sample_title = leaf")):
            self.assertEqual((await server.geo_record("GSM1"))["metadata"]["Sample_characteristics_ch1"], ["treatment: heat"])

    async def test_files_actual_links_and_bounds(self):
        def handler(req):
            self.assertIn("GSE1nnn/GSE1234", req.url.path)
            return httpx.Response(200, text='<a href="../">parent</a><a href="a.txt.gz">a</a><a href="b.txt.gz">b</a>')
        with self.mock_http(handler):
            result = await server.geo_files("GSE1234", 1)
            self.assertEqual(len(result["files"]), 1)
            self.assertTrue(result["truncated"])

    async def test_validation(self):
        for function, arguments in [(server.geo_search, {"query": ""}),
                                    (server.geo_record, {"accession": "../../etc"}),
                                    (server.geo_files, {"accession": "GSE1", "limit": 0})]:
            with self.subTest(tool=function.__name__), self.assertRaises(ValueError):
                await function(**arguments)

    async def test_api_failure_not_silenced(self):
        with self.mock_http(lambda req: httpx.Response(500)):
            with self.assertRaises(httpx.HTTPStatusError):
                await server.geo_record("GSE1")
