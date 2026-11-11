import httpx
from copy import deepcopy

from servers.uniprot_mcp import server
from tests.helpers import HTTPTestCase


MYB52 = {"primaryAccession": "Q6R0C4", "uniProtkbId": "MYB52_ARATH",
         "entryType": "UniProtKB reviewed (Swiss-Prot)",
         "organism": {"taxonId": 3702, "scientificName": "Arabidopsis thaliana"},
         "genes": [{"geneName": {"value": "MYB52"}, "synonyms": [{"value": "AHS1"}],
                    "orderedLocusNames": [{"value": "At1g17950"}]}],
         "proteinDescription": {"recommendedName": {"fullName": {"value": "Transcription factor MYB52"}}},
         "sequence": {"length": 249}, "proteinExistence": "Evidence at transcript level", "annotationScore": 5,
         "comments": [{"commentType": "FUNCTION", "texts": [{"value": "Regulates secondary cell wall biosynthesis.",
                       "evidences": [{"evidenceCode": "ECO:0000269", "source": "PubMed", "id": "18952777"}]}]},
                      {"commentType": "CAUTION", "texts": [{"value": "Positive and negative regulation have both been reported.",
                       "evidences": [{"evidenceCode": "ECO:0000269", "source": "PubMed", "id": "23781226"}]}]},
                      {"commentType": "SUBCELLULAR LOCATION", "subcellularLocations": [{"location": {"value": "Nucleus"}}]}],
         "features": [{"type": "DNA binding", "description": "H-T-H motif",
                       "location": {"start": {"value": 28}, "end": {"value": 51}},
                       "evidences": [{"evidenceCode": "ECO:0000255", "source": "PROSITE-ProRule", "id": "PRU00625"}]}],
         "uniProtKBCrossReferences": [{"database": "GO", "id": "GO:0009834"}],
         "references": [{"citation": {"title": "Secondary wall study", "citationCrossReferences": [
                          {"database": "PubMed", "id": "18952777"}, {"database": "DOI", "id": "10.1105/tpc.108.061325"}]},
                         "referencePositions": ["FUNCTION"]},
                        {"citation": {"title": "Contradictory phenotype study", "citationCrossReferences": [
                          {"database": "PubMed", "id": "23781226"}]}, "referencePositions": ["DISRUPTION PHENOTYPE"]}]}


class UniProtTests(HTTPTestCase):
    async def test_search_pagination(self):
        with self.mock_http(lambda req: httpx.Response(200, json={"results": [{"primaryAccession": "P04637"}]},
                                                      headers={"Link": '<https://rest.uniprot.org/uniprotkb/search?cursor=x>; rel="next"'})):
            result = await server.uniprot_search("gene:TP53", 1)
            self.assertEqual(result["results"][0]["primaryAccession"], "P04637")
            self.assertIn("cursor=x", result["next_url"])

    async def test_entry_and_fasta(self):
        with self.mock_http(lambda req: httpx.Response(200, json={"primaryAccession": "P04637"}) if req.url.path.endswith("json") else httpx.Response(200, text=">P04637\nMEEP")):
            self.assertEqual((await server.uniprot_entry("P04637"))["record"]["primaryAccession"], "P04637")
            self.assertIn("MEEP", (await server.uniprot_sequence("P04637"))["fasta"])

    async def test_mapping_job_lifecycle(self):
        def handler(req):
            if req.method == "POST":
                self.assertIn(b"ids=7157%2C4193", req.content)
                return httpx.Response(200, json={"jobId": "job1"})
            if "status" in req.url.path:
                return httpx.Response(200, json={"results": True})
            return httpx.Response(200, json={"results": [{"from": "7157", "to": "P04637"}], "failedIds": ["bad"]})
        with self.mock_http(handler):
            self.assertEqual((await server.uniprot_mapping_submit(["7157", "4193"]))["jobId"], "job1")
            self.assertTrue((await server.uniprot_mapping_status("job1"))["results"])
            self.assertEqual((await server.uniprot_mapping_results("job1"))["failedIds"], ["bad"])

    async def test_all_tool_validation(self):
        cases = [(server.uniprot_search, {"query": ""}), (server.uniprot_entry, {"accession": "bad"}),
                 (server.uniprot_sequence, {"accession": "../P04637"}), (server.uniprot_mapping_submit, {"ids": []}),
                 (server.uniprot_mapping_status, {"job_id": "../job"}), (server.uniprot_mapping_results, {"job_id": "job1", "limit": 0})]
        for func, args in cases:
            with self.subTest(tool=func.__name__), self.assertRaises(ValueError):
                await func(**args)

    async def test_missing_entry(self):
        with self.mock_http(lambda req: httpx.Response(404)):
            with self.assertRaises(httpx.HTTPStatusError):
                await server.uniprot_entry("P04637")

    async def test_function_exact_gene_species_and_cautions(self):
        def handler(req):
            if req.url.path.endswith("search"):
                self.assertEqual(req.url.params["query"], 'gene_exact:"MYB52" AND organism_id:3702 AND reviewed:true')
                return httpx.Response(200, json={"results": [{"primaryAccession": "Q6R0C4"}]}, headers={"x-total-results": "1"})
            self.assertEqual(req.url.path, "/uniprotkb/Q6R0C4.json")
            return httpx.Response(200, json=MYB52)
        with self.mock_http(handler):
            result = await server.uniprot_function("MYB52", taxon_id=3702)
        self.assertEqual(result["selected_accession"], "Q6R0C4")
        self.assertFalse(result["selection_required"])
        entry = result["entries"][0]
        self.assertEqual(entry["functions"], MYB52["comments"][0]["texts"])
        self.assertEqual(entry["cautions"], [MYB52["comments"][1]])
        self.assertEqual(entry["features"][0]["evidences"][0]["evidenceCode"], "ECO:0000255")
        self.assertEqual([r["pmid"] for r in entry["references"]], ["18952777", "23781226"])
        self.assertIn("23781226", entry["references"][1]["source_url"])
        self.assertEqual(entry["genes"][0]["locus_names"], ["At1g17950"])
        self.assertTrue(entry["reviewed"])

    async def test_function_requires_species_and_preserves_truncation(self):
        def handler(req):
            return (httpx.Response(200, json={"results": [{"primaryAccession": "Q6R0C4"}]},
                                   headers={"x-total-results": "3", "Link": '<https://rest.uniprot.org/uniprotkb/search?cursor=x>; rel="next"'})
                    if req.url.path.endswith("search") else httpx.Response(200, json=MYB52))
        with self.mock_http(handler):
            result = await server.uniprot_function("MYB52", limit=1)
        self.assertTrue(result["selection_required"])
        self.assertIsNone(result["selected_accession"])
        self.assertTrue(result["truncated"])
        self.assertEqual(result["total"], 3)
        self.assertTrue(any("Organism unspecified" in warning for warning in result["warnings"]))

    async def test_function_unreviewed_and_missing_function_remain_explicit(self):
        record = deepcopy(MYB52)
        record["entryType"] = "UniProtKB unreviewed (TrEMBL)"
        record["comments"] = []
        def handler(req):
            if req.url.path.endswith("search"):
                self.assertNotIn("reviewed:", req.url.params["query"])
                return httpx.Response(200, json={"results": [{"primaryAccession": "Q6R0C4"}]})
            return httpx.Response(200, json=record)
        with self.mock_http(handler):
            result = await server.uniprot_function("MYB52", taxon_id=3702, reviewed_only=False)
        entry = result["entries"][0]
        self.assertFalse(entry["reviewed"])
        self.assertEqual(entry["functions"], [])
        self.assertTrue(entry["warnings"])

    async def test_function_partial_failure_keeps_other_candidates(self):
        def handler(req):
            if req.url.path.endswith("search"):
                return httpx.Response(200, json={"results": [{"primaryAccession": "Q6R0C4"}, {"primaryAccession": "P04637"}]})
            return httpx.Response(404) if "P04637" in req.url.path else httpx.Response(200, json=MYB52)
        with self.mock_http(handler):
            result = await server.uniprot_function("MYB52", taxon_id=3702)
        self.assertTrue(result["partial"])
        self.assertEqual(result["entries"][0]["accession"], "Q6R0C4")
        self.assertIsNone(result["selected_accession"])
        self.assertEqual(result["errors"][0]["accession"], "P04637")

    async def test_function_empty_and_validation(self):
        with self.mock_http(lambda req: httpx.Response(200, json={"results": []}, headers={"x-total-results": "0"})):
            result = await server.uniprot_function("UNKNOWN", taxon_id=3702)
        self.assertEqual(result["entries"], [])
        self.assertFalse(result["selection_required"])
        self.assertTrue(result["warnings"])
        for args in ({"gene": ""}, {"gene": 'MYB52 OR *'}, {"gene": "MYB52", "taxon_id": 0},
                     {"gene": "MYB52", "taxon_id": True}, {"gene": "MYB52", "limit": 6},
                     {"gene": "MYB52", "reviewed_only": "yes"}):
            with self.subTest(args=args), self.assertRaises(ValueError):
                await server.uniprot_function(**args)
