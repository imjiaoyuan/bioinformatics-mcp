"""End-to-end discovery contracts with deterministic archive/sample responses."""
import json
from unittest.mock import AsyncMock, patch

import httpx

from common.discovery import filters, assess
from common.ena import files_from_record
from servers.ncbi_mcp import api
from tests.helpers import HTTPTestCase


def run(accession="SRR1", platform="PACBIO_SMRT", **extra):
    return {"run_accession": accession, "study_accession": "PRJNA1", "sample_accession": "SAMN1",
            "scientific_name": "Homo sapiens", "tax_id": "9606", "tissue_type": "liver",
            "library_source": "TRANSCRIPTOMIC", "library_strategy": "RNA-Seq",
            "instrument_platform": platform, "sample_title": "bulk primary tissue liver",
            "fastq_ftp": f"ftp.sra.ebi.ac.uk/{accession}.fastq.gz", "fastq_bytes": "120",
            "fastq_md5": "abc", **extra}


class DiscoveryTests(HTTPTestCase):
    async def test_brain_search_expands_to_cortex_and_uses_specimen_annotations(self):
        def handler(req):
            self.assertIn('"*cerebral cortex*"', req.url.params["query"])
            return httpx.Response(200, json=[run(tissue_type="cerebral cortex")])
        with self.mock_http(handler):
            result = await api.find_data(assay="rna_seq", tissue="brain", archives="ena", metadata_limit=0)
        self.assertEqual(result["candidate_counts"]["match"], 1)
        self.assertEqual(result["candidates"][0]["criteria"]["tissue"]["status"], "match")

    async def test_gsa_business_error_is_a_source_failure(self):
        with self.mock_http(lambda req: httpx.Response(200, json={"code": "500", "message": "failed"})):
            result = await api.find_data(assay="rna_seq", archives="gsa")
        self.assertTrue(result["all_sources_failed"])
        self.assertEqual(result["gsa"]["status"], "error")

    async def test_each_archive_subset_retains_correct_source(self):
        """All 15 subsets cover the original positional task/result misalignment."""
        import itertools
        async def entrez(db, query, max_results=20):
            return {"ids": [], "query": query, "count": 0}
        def handler(req):
            if "ngdc" in req.url.host:
                return httpx.Response(200, json={"result": {"data": {"recordsFiltered": 0, "data": []}}})
            return httpx.Response(200, json=[run()])
        with self.mock_http(handler), patch.object(api, "ncbi_search", side_effect=entrez), \
             patch.object(api, "_taxid", AsyncMock(return_value="9606")):
            for length in range(1, 5):
                for subset in itertools.combinations(("geo", "sra", "ena", "gsa"), length):
                    with self.subTest(archives=subset):
                        result = await api.find_data(organism="human", data_type="rna_seq",
                                                        archives=",".join(subset), metadata_limit=0)
                        self.assertFalse(result["partial"], result["errors"])
                        for name in ("geo", "sra", "ena", "gsa"):
                            self.assertEqual(name in result, name in subset)
                        if "ena" in subset:
                            self.assertEqual(result["ena"]["runs"][0]["run"], "SRR1")

    async def test_missing_ncbi_credentials_do_not_block_ena_and_gsa(self):
        def handler(req):
            return (httpx.Response(200, json={"result": {"data": {"data": [], "recordsFiltered": 0}}})
                    if "ngdc" in req.url.host else httpx.Response(200, json=[run()]))
        with patch.dict("os.environ", {}, clear=True), self.mock_http(handler):
            result = await api.find_data(organism="human", data_type="rna_seq", metadata_limit=0)
        self.assertTrue(result["partial"])
        self.assertEqual(set(result["errors"]), {"geo", "sra"})
        self.assertEqual(result["ena"]["status"], "ok")
        self.assertEqual(result["gsa"]["status"], "ok")
        self.assertFalse(result["all_sources_failed"])

    async def test_ena_tissue_condition_and_transcriptome_fields(self):
        def handler(req):
            q = req.url.params["query"]
            self.assertIn('library_source="TRANSCRIPTOMIC"', q)
            self.assertIn('library_strategy="OTHER"', q)
            self.assertIn('library_strategy="AMPLICON"', q)
            self.assertIn('"*liver*"', q)
            self.assertIn('"*healthy*"', q)
            self.assertIn('instrument_platform="OXFORD_NANOPORE"', q)
            self.assertNotIn("miRNA-Seq", q)
            return httpx.Response(200, json=[run(sample_description="healthy liver")])
        with self.mock_http(handler):
            result = await api.find_data(organism="human", data_type="long_reads", tissue="肝脏",
                                            condition="healthy", archives="ena", metadata_limit=0)
        self.assertEqual(result["candidates"][0]["criteria"]["tissue"]["status"], "match")
        self.assertEqual(result["candidates"][0]["criteria"]["condition"]["status"], "match")

    async def test_hifi_excludes_subreads_and_retains_uncertainty_for_ccs(self):
        rows = [run("SRR1", library_source="GENOMIC", library_strategy="WGS",
                    fastq_ftp="ftp.sra.ebi.ac.uk/SRR1_subreads.fastq.gz"),
                run("SRR2", library_source="GENOMIC", library_strategy="WGS",
                    fastq_ftp="ftp.sra.ebi.ac.uk/SRR2.ccs.fastq.gz"),
                run("SRR3", library_source="GENOMIC", library_strategy="WGS",
                    fastq_ftp="", submitted_ftp="ftp.sra.ebi.ac.uk/SRR3.hifi.bam",
                    submitted_bytes="500", submitted_md5="def")]
        def handler(req):
            self.assertIn("tax_tree(3689)", req.url.params["query"])
            self.assertIn("HiFi", req.url.params["query"])
            self.assertIn('library_strategy="WGS"', req.url.params["query"])
            return httpx.Response(200, json=rows)
        with self.mock_http(handler):
            result = await api.find_data(organism="杨树", assay="wgs", protocol="hifi", archives="ena")
        self.assertEqual(result["candidate_counts"], {"match": 1, "unknown": 1, "mismatch": 1})
        self.assertEqual(result["excluded_candidates"][0]["run"], "SRR1")
        hifi = next(c for c in result["candidates"] if c["run"] == "SRR3")
        self.assertEqual(hifi["files"][0]["format"], "bam")
        self.assertEqual(hifi["files"][0]["bytes"], 500)
        self.assertEqual(hifi["criteria"]["protocol"]["evidence"][-1]["source_url"], hifi["files"][0]["url"])

    async def test_both_technologies_are_queried_and_same_sample_pair_is_verified(self):
        def handler(req):
            if "/browser/api/" in req.url.path:
                return httpx.Response(200, text="<SAMPLE_SET/>")
            q = req.url.params["query"]
            short = 'instrument_platform="ILLUMINA"' in q
            return httpx.Response(200, json=[run("SRR1" if short else "SRR2", "ILLUMINA" if short else "PACBIO_SMRT")])
        with self.mock_http(handler):
            result = await api.find_data(organism="human", assay="rna_seq", tissue="liver",
                                            read_type="both", pairing="same_sample", archives="ena", limit=1)
        self.assertEqual(len(result["ena"]["pages"]), 2)
        self.assertTrue(result["truncated"])
        self.assertEqual(result["candidate_counts"]["match"], 2)
        self.assertEqual(len(result["pair_groups"]), 1)
        self.assertTrue(result["pair_groups"][0]["identity_verified"])

    async def test_same_project_or_tissue_does_not_establish_pairing(self):
        rows = [run("SRR1", "ILLUMINA", sample_accession="SAMN1"),
                run("SRR2", sample_accession="SAMN2")]
        with self.mock_http(lambda req: httpx.Response(200, json=rows)):
            result = await api.find_data(organism="human", assay="rna_seq", pairing="same_sample", archives="ena")
        self.assertEqual(result["pair_groups"], [])
        self.assertTrue(all(c["criteria"]["pairing"]["status"] == "unknown" for c in result["candidates"]))

    async def test_donor_is_read_from_sample_xml_and_scoped_to_study(self):
        rows = [run("SRR1", "ILLUMINA", sample_accession="SAMN1"),
                run("SRR2", sample_accession="SAMN2")]
        def handler(req):
            if "/browser/api/" in req.url.path:
                return httpx.Response(200, text='<SAMPLE_SET><SAMPLE><SAMPLE_ATTRIBUTES><SAMPLE_ATTRIBUTE>'
                                      '<TAG>donor_id</TAG><VALUE>D1</VALUE></SAMPLE_ATTRIBUTE>'
                                      '</SAMPLE_ATTRIBUTES></SAMPLE></SAMPLE_SET>')
            return httpx.Response(200, json=rows)
        with self.mock_http(handler):
            result = await api.find_data(organism="human", assay="rna_seq", pairing="same_donor", archives="ena")
        self.assertEqual(result["pair_groups"][0]["identity"], ["PRJNA1", "D1"])
        rows[1]["study_accession"] = "PRJNA2"
        with self.mock_http(handler):
            result = await api.find_data(organism="human", assay="rna_seq", pairing="same_donor", archives="ena")
        self.assertEqual(result["pair_groups"], [])

    async def test_study_title_cannot_prove_tissue_or_protocol(self):
        row = run(study_title="liver HiFi", sample_title="sample A", tissue_type="", sample_description="")
        with self.mock_http(lambda req: httpx.Response(200, json=[row])):
            result = await api.find_data(organism="human", assay="rna_seq", tissue="liver",
                                            protocol="hifi", archives="ena", metadata_limit=0)
        candidate = result["candidates"][0]
        self.assertEqual(candidate["criteria"]["tissue"]["status"], "unknown")
        self.assertEqual(candidate["criteria"]["protocol"]["status"], "unknown")

    async def test_invalid_json_is_source_error_not_empty_success(self):
        with self.mock_http(lambda req: httpx.Response(200, text="<html>service unavailable</html>")):
            result = await api.find_data(organism="human", assay="rna_seq", archives="ena")
        self.assertTrue(result["partial"])
        self.assertTrue(result["all_sources_failed"])
        self.assertEqual(result["ena"]["status"], "error")

    async def test_summary_failure_preserves_search_hits_and_does_not_leak_key(self):
        with patch.object(api, "ncbi_search", AsyncMock(return_value={"ids": ["1"], "count": 3})), \
             patch.object(api, "ncbi_summary", AsyncMock(side_effect=RuntimeError("secret-api-key"))):
            result = await api.find_data(assay="rna_seq", archives="sra")
        self.assertEqual(result["sra"]["ids"], ["1"])
        self.assertTrue(result["partial"])
        self.assertNotIn("secret-api-key", json.dumps(result))

    async def test_validation_before_network(self):
        cases = [{"platforms": ["invalid"]}, {"assay": "invalid"}, {"protocol": "invalid"},
                 {"protocol": "hifi", "platforms": ["ont"]}, {"protocol": "hifi", "read_type": "short"},
                 {"tissue": 'liver" OR tax_eq(1)'}, {"offset": -1}, {"metadata_limit": 21},
                 {"sample_scope": "invalid"}, {"pairing": "invalid"}, {"file_format": "invalid"},
                 {"data_type": "ont", "protocol": "hifi"}, {"assay": "wgs", "protocol": "direct_rna"},
                 {"data_type": "rna_seq", "assay": "wgs"}]
        with patch.object(api, "request", AsyncMock()) as request:
            for case in cases:
                with self.subTest(case=case), self.assertRaises(ValueError):
                    await api.find_data(condition="test", **case)
            request.assert_not_awaited()

    async def test_single_source_download_plans_and_partial_failure(self):
        sra = [{"run": "SRR1", "download_url": "https://example.org/SRR1", "size_mb": 1}]
        with patch.object(api, "_geo_file_urls", AsyncMock(return_value=["https://example.org/a.gz"])), \
             patch.object(api, "_sra_runs_for_accessions", AsyncMock(return_value=sra)):
            geo = await api.download_plan(["gse1"])
            raw = await api.download_plan(["SRR1"])
        self.assertEqual(geo["items"][0]["source"], "geo")
        self.assertEqual(raw["items"][0]["source"], "sra")
        with patch.object(api, "_geo_file_urls", AsyncMock(side_effect=RuntimeError("down"))), \
             patch.object(api, "_sra_runs_for_accessions", AsyncMock(return_value=sra)):
            result = await api.download_plan(["GSE1", "SRR1"])
        self.assertTrue(result["partial"])
        self.assertEqual(result["items"][0]["accession"], "SRR1")

    async def test_malformed_file_vectors_do_not_assign_wrong_checksums(self):
        files, warnings = files_from_record({"fastq_ftp": "host/a;host/b", "fastq_md5": "one", "fastq_bytes": "10;20"})
        self.assertEqual([x["md5"] for x in files], [None, None])
        self.assertEqual([x["bytes"] for x in files], [10, 20])
        self.assertTrue(warnings)

    async def test_protocol_and_assay_contradictions_are_not_matches(self):
        f = filters("human", "", "", assay="rna_seq", protocol="direct_rna")
        candidate = {"id": "ena:SRR1", "source_url": "https://example.org/SRR1", "files": [],
                     "metadata": run(platform="OXFORD_NANOPORE", library_strategy="miRNA-Seq",
                                     library_construction_protocol="PCR-cDNA")}
        assessed = assess(candidate, f)
        self.assertEqual(assessed["criteria"]["assay"]["status"], "mismatch")
        self.assertEqual(assessed["criteria"]["protocol"]["status"], "mismatch")

    async def test_hifi_metadata_conflicting_with_filename_is_explicit(self):
        row = run(library_source="GENOMIC", library_strategy="WGS", experiment_title="PacBio HiFi genome",
                  fastq_ftp="host/SRR1_subreads.fastq.gz")
        with self.mock_http(lambda req: httpx.Response(200, json=[row])):
            result = await api.find_data(assay="wgs", protocol="hifi", archives="ena")
        c = result["candidates"][0]
        self.assertEqual(c["criteria"]["protocol"]["status"], "match")
        self.assertEqual(c["criteria"]["read_representation"]["status"], "unknown")
        self.assertEqual(c["status"], "unknown")

    async def test_both_with_long_read_protocol_does_not_filter_out_short_partner(self):
        def handler(req):
            q = req.url.params["query"]
            short = 'instrument_platform="ILLUMINA"' in q
            self.assertEqual("HiFi" in q, not short)
            return httpx.Response(200, json=[run("SRR1" if short else "SRR2", "ILLUMINA" if short else "PACBIO_SMRT",
                                                  experiment_title="RNA-seq" if short else "HiFi Iso-Seq")])
        with self.mock_http(handler):
            result = await api.find_data(assay="rna_seq", read_type="both", protocol="hifi",
                                            platforms=["illumina", "pacbio"], pairing="same_sample", archives="ena")
        self.assertFalse(result["errors"])
        self.assertEqual(result["candidate_counts"]["match"], 2)
        self.assertEqual(len(result["pair_groups"]), 1)

    async def test_one_ena_window_failure_keeps_other_technology(self):
        def handler(req):
            q = req.url.params["query"]
            return httpx.Response(400) if "OXFORD_NANOPORE" in q else httpx.Response(200, json=[run("SRR1", "ILLUMINA")])
        with self.mock_http(handler):
            result = await api.find_data(assay="rna_seq", read_type="both", archives="ena")
        self.assertTrue(result["partial"])
        self.assertEqual(result["ena"]["runs"][0]["run"], "SRR1")
        self.assertEqual(result["ena"]["pages"][1]["status"], "error")

    async def test_offset_sample_enrichment_bound_and_underscore_tissue(self):
        samples = []
        def handler(req):
            if "/browser/api/" in req.url.path:
                samples.append(req.url.path)
                return httpx.Response(200, text="<SAMPLE_SET/>")
            self.assertEqual(req.url.params["offset"], "10")
            return httpx.Response(200, json=[run("SRR1", sample_accession="SAMN1", tissue_type="", sample_title="human_liver"),
                                                  run("SRR2", sample_accession="SAMN2", tissue_type="", sample_title="human_liver")])
        with self.mock_http(handler):
            result = await api.find_data(assay="rna_seq", tissue="liver", offset=10, limit=2, metadata_limit=1, archives="ena")
        self.assertEqual(len(samples), 1)
        self.assertEqual(result["ena"]["pages"][0]["next_offset"], 12)
        self.assertTrue(all(c["criteria"]["tissue"]["status"] == "match" for c in result["candidates"]))
        self.assertIn("enrichment", result["candidates"][1]["warnings"][0])

    async def test_cell_line_is_excluded_when_primary_tissue_requested(self):
        with self.mock_http(lambda req: httpx.Response(200, json=[run(cell_line="Huh7")])):
            result = await api.find_data(assay="rna_seq", tissue="liver", sample_type="tissue", archives="ena", metadata_limit=0)
        self.assertEqual(result["candidate_counts"]["mismatch"], 1)
        self.assertEqual(result["excluded_candidates"][0]["criteria"]["sample_type"]["status"], "mismatch")

    async def test_summary_xml_produces_sra_run_candidates(self):
        summary = {"1": {"expxml": '<Summary><Title>bulk liver RNA</Title><Platform instrument_model="NovaSeq">ILLUMINA</Platform></Summary>'
                                    '<Experiment acc="SRX1"/><Study acc="SRP1"/><Sample acc="SRS1"/>'
                                    '<Biosample>SAMN1</Biosample><Library_descriptor><LIBRARY_STRATEGY>RNA-Seq</LIBRARY_STRATEGY>'
                                    '<LIBRARY_SOURCE>TRANSCRIPTOMIC</LIBRARY_SOURCE></Library_descriptor>',
                          "runs": '<Run acc="SRR1"/><Run acc="SRR2"/>'}}
        with patch.object(api, "ncbi_search", AsyncMock(return_value={"ids": ["1"], "count": 1})), \
             patch.object(api, "ncbi_summary", AsyncMock(return_value={"result": summary})):
            result = await api.find_data(assay="rna_seq", archives="sra")
        self.assertEqual([c["run"] for c in result["candidates"]], ["SRR1", "SRR2"])
        self.assertTrue(all(c["metadata"]["biosample"] == "SAMN1" for c in result["candidates"]))

    async def test_source_http_error_is_reported_without_credentials(self):
        req = httpx.Request("GET", "https://example.org/?api_key=private")
        exc = httpx.HTTPStatusError("private", request=req, response=httpx.Response(429, request=req))
        with patch.object(api, "_ena_section", AsyncMock(side_effect=exc)):
            result = await api.find_data(assay="rna_seq", archives="ena")
        self.assertEqual(result["errors"]["ena"]["status_code"], 429)
        self.assertNotIn("private", json.dumps(result))
