import json
from unittest.mock import AsyncMock, patch

import httpx

from servers.alliance_mcp import api
from tests.helpers import HTTPTestCase


def _gene_payload() -> dict:
    return {
        "category": "gene_summary",
        "searchable": False,
        "gene": {
            "type": "Gene",
            "curie": "AGRKB:105000000213379",
            "primaryExternalId": "WB:WBGene00003055",
            "dataProvider": {"type": "AllianceMember", "abbreviation": "WB",
                             "fullName": "WormBase"},
            "dataProviderCrossReference": {"referencedCurie": "WB:WBGene00003055",
                                           "displayName": "WBGene00003055"},
            "taxon": {"curie": "NCBITaxon:6239", "name": "Caenorhabditis elegans",
                      "descendantCount": 0,
                      "species": {"fullName": "Caenorhabditis elegans",
                                  "abbreviation": "Cel", "displayName": "WB"}},
            "crossReferences": [{"referencedCurie": "NCBI_Gene:175753",
                                 "displayName": "GEO"}],
            "geneType": {"curie": "SO:0001217", "name": "protein_coding_gene"},
            "geneSymbol": {"formatText": "lin-4", "displayText": "lin-4"},
            "geneFullName": {"formatText": "lin-4", "displayText": "lin-4"},
            "geneSystematicName": {"formatText": "F48C8.1", "displayText": "F48C8.1"},
            "geneSynonyms": [{"formatText": "CELE_F48E8.1", "displayText": "CELE_F48E8.1"}],
            "geneSecondaryIds": [],
            "geneGenomicLocationAssociations": [],
        },
        "referenceCuries": ["AGRKB:101000000622122"],
    }


class AllianceTests(HTTPTestCase):
    async def test_gene_summary_success_exact_keys(self):
        with self.mock_http(lambda req: httpx.Response(200, json=_gene_payload())), \
                patch("common.http.asyncio.sleep", new_callable=AsyncMock):
            result = await api.alliance_gene("WB:WBGene00003055")
        self.assertEqual(result["status"], "ok")
        self.assertIn("alliancegenome.org/api/gene/WB:WBGene00003055", result["source_url"])
        data = result["data"]
        self.assertEqual(data["curie"], "AGRKB:105000000213379")
        self.assertEqual(data["primary_external_id"], "WB:WBGene00003055")
        self.assertEqual(data["symbol"], "lin-4")
        self.assertEqual(data["systematic_name"], "F48C8.1")
        self.assertEqual(data["gene_type"], "protein_coding_gene")
        self.assertEqual(data["so_term_id"], "SO:0001217")
        self.assertEqual(data["taxon"]["curie"], "NCBITaxon:6239")
        self.assertEqual(data["taxon"]["species"], "Caenorhabditis elegans")
        self.assertEqual(data["data_provider"], {"abbreviation": "WB",
                                                 "full_name": "WormBase"})
        self.assertEqual(data["cross_references"][0]["referenced_curie"], "NCBI_Gene:175753")
        self.assertEqual(data["synonyms"], ["CELE_F48E8.1"])
        self.assertEqual(result["gene"]["type"], "Gene")

    async def test_bare_mod_ids_normalized_to_member_prefixes(self):
        seen = []

        def handler(req):
            seen.append(req.url.path)
            return httpx.Response(200, json=_gene_payload())

        with self.mock_http(handler), patch("common.http.asyncio.sleep", new_callable=AsyncMock):
            for value in ["FBgn0000606", "WBGene00003055", "ZDB-GENE-990415-72",
                          "SGD:S000006158", "mgi:98297", "RGD:3889", "AGRKB:105000000213379"]:
                result = await api.alliance_gene(value)
                self.assertEqual(result["status"], "ok")
        self.assertEqual(seen[0], "/api/gene/FB:FBgn0000606")
        self.assertEqual(seen[1], "/api/gene/WB:WBGene00003055")
        self.assertEqual(seen[2], "/api/gene/ZFIN:ZDB-GENE-990415-72")
        self.assertEqual(seen[3], "/api/gene/SGD:S000006158")
        self.assertEqual(seen[4], "/api/gene/MGI:98297")
        self.assertEqual(seen[5], "/api/gene/RGD:3889")
        self.assertEqual(seen[6], "/api/gene/AGRKB:105000000213379")

    async def test_invalid_gene_ids_rejected(self):
        for bad in ["", "TP53", "FBgn000060", "WBGene0000305", "HGNC", "HGNC:", ":11998",
                    "NCBITaxon:9606;DROP", "FBgn0000606 OR 1=1", "bad id", "S00000",
                    "MGI98297", "gene\nHGNC:11998"]:
            with self.subTest(gene_id=bad), self.assertRaises(ValueError):
                await api.alliance_gene(bad)

    async def test_unknown_gene_returns_not_found(self):
        with self.mock_http(lambda req: httpx.Response(404, json={"error": "not found"})), \
                patch("common.http.asyncio.sleep", new_callable=AsyncMock):
            result = await api.alliance_gene("HGNC:999999999")
        self.assertEqual(result["status"], "not_found")
        self.assertNotIn("data", result)

    async def test_upstream_400_mapped_to_value_error_and_missing_payload(self):
        with self.mock_http(lambda req: httpx.Response(400, json={"statusCode": 400})), \
                patch("common.http.asyncio.sleep", new_callable=AsyncMock):
            with self.assertRaises(ValueError):
                await api.alliance_gene("HGNC:11998")
        with self.mock_http(lambda req: httpx.Response(200, json={})), \
                patch("common.http.asyncio.sleep", new_callable=AsyncMock):
            self.assertEqual((await api.alliance_gene("HGNC:11998"))["status"], "not_found")

    async def test_phenotypes_success_with_verified_shape(self):
        payload = {
            "results": [{
                "subject": {"curie": "AGRKB:105000000331364",
                            "primaryExternalId": "HGNC:11998"},
                "relation": {"id": 200000000, "name": "has_phenotype"},
                "primaryAnnotations": [{
                    "type": "GenePhenotypeAnnotation",
                    "uniqueId": "HGNC:11998|has_phenotype|Abdominal obesity|HP:0012743",
                    "curie": "AGRKB:116000000911606",
                    "dataProvider": {"type": "AllianceMember", "abbreviation": "RGD",
                                     "fullName": "Rat Genome Database"},
                    "evidenceItem": {"type": "ExternalDatabaseReference",
                                     "curie": "ORPHA:96253"},
                }],
                "category": "phenotype_annotation",
                "searchable": False,
                "uniqueId": "vcAggaEBqU01CWvCrejU",
                "phenotypeStatement": "Abdominal obesity",
                "references": [{"referencedCurie": "PMID:12345678"}],
                "pubmedPublications": [{"referencedCurie": "PMID:12345678"}],
            }],
            "total": 225,
            "returnedRecords": 1,
        }
        with self.mock_http(lambda req: httpx.Response(200, json=payload)), \
                patch("common.http.asyncio.sleep", new_callable=AsyncMock):
            result = await api.alliance_gene_phenotypes("HGNC:11998", limit=10, offset=0)
        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["upstream_total"], 225)
        self.assertEqual(result["total"], 1)
        row = result["results"][0]
        self.assertEqual(row["phenotype_statement"], "Abdominal obesity")
        self.assertEqual(row["relation"], "has_phenotype")
        self.assertEqual(row["annotation_curies"], ["AGRKB:116000000911606"])
        self.assertEqual(row["data_providers"], ["RGD"])
        self.assertEqual(row["evidence_curies"], ["ORPHA:96253"])
        self.assertIn("alliancegenome.org/api/gene/HGNC:11998/phenotypes", result["source_url"])

    async def test_orthologs_success_with_verified_shape(self):
        payload = {"results": [{
            "category": "gene_to_gene_orthology",
            "searchable": False,
            "stringencyFilter": "stringent",
            "geneAnnotations": [{"geneIdentifier": "HGNC:11998"},
                                {"geneIdentifier": "RGD:3889"}],
            "geneToGeneOrthologyGenerated": {
                "subjectGene": {"type": "Gene", "curie": "AGRKB:105000000331364",
                                "primaryExternalId": "HGNC:11998",
                                "geneSymbol": {"displayText": "TP53"},
                                "taxon": {"curie": "NCBITaxon:9606",
                                          "species": {"fullName": "Homo sapiens"}}},
                "objectGene": {"type": "Gene", "curie": "AGRKB:105000000502825",
                               "primaryExternalId": "RGD:3889",
                               "geneSymbol": {"displayText": "Tp53"},
                               "taxon": {"curie": "NCBITaxon:10116",
                                         "species": {"fullName": "Rattus norvegicus"}}},
                "isBestScore": {"name": "Yes"},
                "isBestScoreReverse": {"name": "Yes"},
                "confidence": {"name": "high"},
                "predictionMethodsMatched": [{"name": "PANTHER"}, {"name": "HGNC"},
                                             {"name": "OMA"}],
                "predictionMethodsNotMatched": [{"name": "Ensembl Compara"}],
            }}],
            "total": 7, "returnedRecords": 7}
        with self.mock_http(lambda req: httpx.Response(200, json=payload)), \
                patch("common.http.asyncio.sleep", new_callable=AsyncMock):
            result = await api.alliance_orthologs("HGNC:11998")
        self.assertEqual(result["status"], "ok")
        row = result["results"][0]
        self.assertEqual(row["subject_gene"]["primary_external_id"], "HGNC:11998")
        self.assertEqual(row["object_gene"]["primary_external_id"], "RGD:3889")
        self.assertEqual(row["object_gene"]["species"], "Rattus norvegicus")
        self.assertEqual(row["confidence"], "high")
        self.assertEqual(row["best_score"], "Yes")
        self.assertEqual(row["methods_matched"], ["PANTHER", "HGNC", "OMA"])
        self.assertEqual(row["source_member_databases"], ["HGNC"])
        self.assertIn("/orthologs", result["source_url"])

    async def test_empty_lists_are_not_errors(self):
        with self.mock_http(lambda req: httpx.Response(
                200, json={"results": [], "total": 0, "returnedRecords": 0})), \
                patch("common.http.asyncio.sleep", new_callable=AsyncMock):
            for tool in (api.alliance_gene_phenotypes, api.alliance_orthologs):
                with self.subTest(tool=tool.__name__):
                    result = await tool("WB:WBGene00003055")
                    self.assertEqual(result["status"], "ok")
                    self.assertEqual(result["total"], 0)
                    self.assertEqual(result["results"], [])

    async def test_local_pagination(self):
        rows = [{"phenotypeStatement": f"phenotype {index}",
                 "relation": {"name": "has_phenotype"}, "primaryAnnotations": [],
                 "references": [], "pubmedPublications": []} for index in range(30)]
        with self.mock_http(lambda req: httpx.Response(
                200, json={"results": rows, "total": 30, "returnedRecords": 30})), \
                patch("common.http.asyncio.sleep", new_callable=AsyncMock):
            first = await api.alliance_gene_phenotypes("HGNC:11998", limit=10, offset=0)
            second = await api.alliance_gene_phenotypes("HGNC:11998", limit=10, offset=10)
            tail = await api.alliance_gene_phenotypes("HGNC:11998", limit=10, offset=20)
            past = await api.alliance_gene_phenotypes("HGNC:11998", limit=10, offset=30)
        self.assertEqual(first["results"][0]["phenotype_statement"], "phenotype 0")
        self.assertEqual(second["results"][0]["phenotype_statement"], "phenotype 10")
        self.assertEqual(tail["total"], 30)
        self.assertTrue(second["truncated"])
        self.assertEqual(tail["pagination"], "local")
        self.assertFalse(tail["truncated"])
        self.assertEqual(past["results"], [])
        for bad in ({"gene_id": "HGNC:11998", "limit": 0},
                    {"gene_id": "HGNC:11998", "limit": 101},
                    {"gene_id": "HGNC:11998", "offset": -1},
                    {"gene_id": "HGNC:11998", "offset": 1_000_001}):
            with self.subTest(args=bad), self.assertRaises(ValueError):
                await api.alliance_gene_phenotypes(**bad)

    async def test_search_preserves_upstream_pagination(self):
        payload = {
            "aggregations": [{"key": "category", "values": [
                {"key": "variant_search_result", "total": 17139},
                {"key": "literature_search_result", "total": 13766},
                {"key": "gene_search_result", "total": 1168},
                {"key": "allele_search_result", "total": 750},
                {"key": "disease_search_result", "total": 139}]}],
            "results": [
                {"id": "FB:FBgn0039044", "curie": "FB:FBgn0039044",
                 "category": "gene_search_result", "symbol": "p53",
                 "name": "p53", "species": "Drosophila melanogaster",
                 "soTermName": "protein_coding_gene", "score": 1100475.5},
                {"id": "MGI:104672", "curie": "MGI:104672",
                 "category": "disease_search_result", "symbol": None,
                 "name": "p53 deficiency", "species": None,
                 "soTermName": None, "score": 12.5}],
            "total": 33578,
        }
        requests = []

        def handler(req):
            requests.append(req)
            return httpx.Response(200, json=payload)

        with self.mock_http(handler), patch("common.http.asyncio.sleep", new_callable=AsyncMock):
            result = await api.alliance_search("p53", limit=2, offset=40)
            self.assertEqual(requests[0].url.params["q"], "p53")
            self.assertNotIn("category", requests[0].url.params)
            self.assertEqual(requests[0].url.params["limit"], "2")
            self.assertEqual(requests[0].url.params["offset"], "40")
            self.assertEqual(result["status"], "ok")
            self.assertEqual(result["total"], 33578)
            self.assertEqual(result["category_totals"]["gene_search_result"], 1168)
            self.assertEqual(result["category_totals"]["disease_search_result"], 139)
            self.assertEqual(result["pagination"], "upstream")
            self.assertEqual(result["results"][0]["id"], "FB:FBgn0039044")
            self.assertEqual(result["results"][0]["species"], "Drosophila melanogaster")
            self.assertIn("alliancegenome.org/api/search", result["source_url"])
            filtered = await api.alliance_search("p53", category="disease_search_result")
            self.assertEqual(filtered["category"], "disease_search_result")
            self.assertEqual(filtered["total"], 1)
            self.assertEqual(filtered["results"][0]["name"], "p53 deficiency")
            self.assertEqual(filtered["pagination"], "local")

    async def test_search_validation(self):
        for args in [{"query": ""}, {"query": "p53", "limit": 0},
                     {"query": "p53", "limit": 101}, {"query": "x" * 301},
                     {"query": "p53", "category": 5}]:
            with self.subTest(args=args), self.assertRaises(ValueError):
                await api.alliance_search(**args)

    async def test_alleles_success_with_provisional_shape(self):
        payload = {"results": [
            {"id": "WB:WBVar00059878", "curie": "WB:WBVar00059878",
             "category": "allele_search_result", "symbol": "lin-4(sd127)",
             "name": "lin-4", "species": "Caenorhabditis elegans"},
            {"id": "WB:WBVar00274874", "curie": "WB:WBVar00274874",
             "category": "allele_search_result", "symbol": None, "name": None,
             "species": None}],
            "total": 2, "returnedRecords": 2}

        def handler(req):
            self.assertIn("/alleles", req.url.path)
            return httpx.Response(200, json=payload)

        with self.mock_http(handler), patch("common.http.asyncio.sleep", new_callable=AsyncMock):
            result = await api.alliance_alleles("WB:WBGene00003055", limit=1, offset=0)
        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["upstream_total"], 2)
        self.assertEqual(result["total"], 2)
        self.assertEqual(len(result["results"]), 1)
        self.assertTrue(result["truncated"])
        self.assertEqual(result["results"][0]["id"], "WB:WBVar00059878")
        self.assertEqual(result["results"][0]["category"], "allele_search_result")
        self.assertIn("/alleles", result["source_url"])

    async def test_alleles_falls_back_to_allele_search_on_404(self):
        allele_payload = {"results": [
            {"id": "FBal0000127", "curie": "FB:FBal0000127",
             "category": "allele_search_result", "symbol": "sd",
             "name": "scabrous", "species": "Drosophila melanogaster"}],
            "total": 1, "returnedRecords": 1}
        paths = []

        def handler(req):
            paths.append(req.url.path)
            if "/alleles" in req.url.path:
                return httpx.Response(404, json={"error": "Resource not found"})
            self.assertEqual(req.url.path, "/api/allele/search")
            return httpx.Response(200, json=allele_payload)

        with self.mock_http(handler), patch("common.http.asyncio.sleep", new_callable=AsyncMock):
            result = await api.alliance_alleles("FB:FBgn0000606")
        self.assertEqual(paths, ["/api/gene/FB:FBgn0000606/alleles", "/api/allele/search"])
        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["results"][0]["curie"], "FB:FBal0000127")
        self.assertIn("/allele/search", result["source_url"])

    async def test_alleles_validates_before_network_request(self):
        with patch.object(api, "_get") as get:
            for args in [{"gene_id": "HGNC:11998", "limit": 0},
                         {"gene_id": "HGNC:11998", "limit": 101},
                         {"gene_id": "HGNC:11998", "offset": -1},
                         {"gene_id": "HGNC:11998", "offset": 1_000_001},
                         {"gene_id": "TP53"}]:
                with self.subTest(args=args), self.assertRaises(ValueError):
                    await api.alliance_alleles(**args)
            get.assert_not_called()

    async def test_disease_search_filters_category_locally(self):
        payload = {
            "aggregations": [{"key": "category", "values": [
                {"key": "gene_search_result", "total": 1168},
                {"key": "allele_search_result", "total": 750},
                {"key": "disease_search_result", "total": 139}]}],
            "results": [
                {"id": "FB:FBgn0039044", "curie": "FB:FBgn0039044",
                 "category": "gene_search_result", "symbol": "p53",
                 "name": "p53", "species": "Drosophila melanogaster",
                 "soTermName": "protein_coding_gene", "score": 1100475.5},
                {"id": "MGI:104672", "curie": "MGI:104672",
                 "category": "disease_search_result", "symbol": None,
                 "name": "p53 deficiency", "species": None,
                 "soTermName": None, "score": 12.5},
                {"id": "WB:WBVar00059878", "curie": "WB:WBVar00059878",
                 "category": "allele_search_result", "symbol": "lin-4",
                 "name": "lin-4", "species": "Caenorhabditis elegans",
                 "soTermName": None, "score": 5.0}],
            "total": 2057,
        }
        requests = []

        def handler(req):
            requests.append(req)
            return httpx.Response(200, json=payload)

        with self.mock_http(handler), patch("common.http.asyncio.sleep", new_callable=AsyncMock):
            result = await api.alliance_disease_search("p53", limit=2)
            self.assertEqual(requests[0].url.params["q"], "p53")
            self.assertNotIn("category", requests[0].url.params)
            self.assertEqual(requests[0].url.params["limit"], "2")
            self.assertEqual(requests[0].url.params["offset"], "0")
        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["category"], "disease_search_result")
        self.assertEqual(result["category_totals"]["disease_search_result"], 139)
        self.assertEqual(result["pagination"], "local")
        self.assertEqual([row["name"] for row in result["results"]], ["p53 deficiency"])

    async def test_disease_search_validates_before_network_request(self):
        with patch.object(api, "_get") as get:
            for args in [{"query": ""}, {"query": "p53", "limit": 0},
                         {"query": "p53", "limit": 101},
                         {"query": "p53", "offset": -1},
                         {"query": "p53", "offset": 1_000_001}]:
                with self.subTest(args=args), self.assertRaises(ValueError):
                    await api.alliance_disease_search(**args)
            get.assert_not_called()

    async def test_upstream_5xx_propagates(self):
        with self.mock_http(lambda req: httpx.Response(500)), \
                patch("common.http.asyncio.sleep", new_callable=AsyncMock):
            with self.assertRaises(httpx.HTTPStatusError):
                await api.alliance_gene("HGNC:11998")

    async def test_tools_exported(self):
        self.assertEqual([tool.__name__ for tool in api.TOOLS],
                         ["alliance_gene", "alliance_gene_phenotypes",
                          "alliance_orthologs", "alliance_search",
                          "alliance_disease_search", "alliance_alleles"])
        self.assertEqual(api.RESOURCES, ())
