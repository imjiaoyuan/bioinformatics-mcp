import json
from unittest import mock

import httpx

from servers.datasets_mcp import api
from tests.helpers import HTTPTestCase


def genome_report(accession="GCF_000001735.4", level="Chromosome"):
    return {"accession": accession, "current_accession": accession,
            "paired_accession": "GCA_000001735.2", "source_database": "SOURCE_DATABASE_REFSEQ",
            "organism": {"tax_id": 3702, "organism_name": "Arabidopsis thaliana",
                         "common_name": "thale cress"},
            "assembly_info": {"assembly_level": level, "assembly_status": "current",
                              "assembly_name": "TAIR10.1"}}


def genome_page(reports, token=None, total=None):
    data = {"reports": reports}
    if total is not None:
        data["total_count"] = total
    if token is not None:
        data["next_page_token"] = token
    return data


class DatasetTests(HTTPTestCase):
    async def test_assemblies_success_and_filters(self):
        def handler(req):
            self.assertTrue(req.url.path.endswith("/genome/taxon/3702/dataset_report"))
            self.assertEqual(req.url.params["filters.assembly_source"], "refseq")
            self.assertEqual(req.url.params["filters.assembly_level"], "chromosome")
            self.assertEqual(req.url.params["page_size"], "20")
            return httpx.Response(200, json=genome_page([genome_report()], total=1))
        with self.mock_http(handler):
            result = await api.dataset_assemblies("3702", source="refseq", level="chromosome")
        self.assertEqual(result["reports"][0]["accession"], "GCF_000001735.4")
        self.assertEqual(result["reports"][0]["organism"]["common_name"], "thale cress")
        self.assertFalse(result["truncated"])
        self.assertEqual(result["source_url"], api.BASE + "/genome/taxon/3702/dataset_report")

    async def test_assemblies_upstream_token_pagination(self):
        pages = [genome_page([genome_report(f"GCF_{i}.1") for i in range(2)], token="tok1", total=5),
                 genome_page([genome_report(f"GCF_{i}.1") for i in range(2, 3)])]

        def handler(req):
            page = pages.pop(0)
            if "page_token" in str(req.url):
                self.assertEqual(req.url.params["page_token"], "tok1")
            return httpx.Response(200, json=page)
        with self.mock_http(handler):
            result = await api.dataset_assemblies("arabidopsis thaliana", limit=4)
        # First page (2 rows) is below offset+limit, so the token page is followed.
        self.assertEqual(len(pages), 0)
        self.assertEqual(len(result["reports"]), 3)
        self.assertFalse(result["truncated"])

    async def test_assemblies_offset_slice(self):
        reports = [genome_report(f"GCA_{i}.1") for i in range(6)]

        def handler(req):
            self.assertEqual(req.url.params["page_size"], "6")
            return httpx.Response(200, json=genome_page(reports, token="more", total=20))
        with self.mock_http(handler):
            result = await api.dataset_assemblies("3702", limit=2, offset=4)
        self.assertEqual([r["accession"] for r in result["reports"]], ["GCA_4.1", "GCA_5.1"])
        self.assertTrue(result["truncated"])  # upstream still has a token

    async def test_assembly_single(self):
        def handler(req):
            self.assertTrue(req.url.path.endswith("/genome/accession/GCF_000001735.4/dataset_report"))
            return httpx.Response(200, json=genome_page([genome_report()]))
        with self.mock_http(handler):
            result = await api.dataset_assembly("gcf_000001735.4")
        self.assertEqual(result["report"]["assembly_info"]["assembly_name"], "TAIR10.1")
        with self.assertRaises(ValueError):
            await api.dataset_assembly("NC_000001.1")
        with self.assertRaises(ValueError):
            await api.dataset_assembly("GCF_000001735")  # missing version

    async def test_assembly_404_mapped(self):
        with self.assertRaises(ValueError) as ctx:
            with self.mock_http(lambda req: httpx.Response(404)):
                await api.dataset_assembly("GCF_999999999.1")
        self.assertIn("Unknown assembly accession", str(ctx.exception))
        with self.assertRaises(httpx.HTTPStatusError):
            with self.mock_http(lambda req: httpx.Response(500)):
                await api.dataset_assembly("GCF_000001735.4")

    async def test_genes_by_symbol(self):
        def handler(req):
            self.assertTrue(req.url.path.endswith("/gene/symbol/FLC/taxon/3702/dataset_report"))
            report = {"gene": {"gene_id": "830878", "symbol": "FLC", "tax_id": "3702",
                               "taxname": "Arabidopsis thaliana", "type": "PROTEIN_CODING",
                               "chromosomes": ["5"]}}
            return httpx.Response(200, json={"reports": [report], "total_count": 1})
        with self.mock_http(handler):
            result = await api.dataset_genes("3702", symbol="FLC")
        self.assertEqual(result["reports"][0]["gene"]["symbol"], "FLC")
        self.assertIn("symbol", result)
        self.assertFalse(result["truncated"])

    async def test_genes_by_id_and_warning_messages(self):
        def handler(req):
            self.assertTrue(req.url.path.endswith("/gene/id/830878/dataset_report"))
            return httpx.Response(200, json={"reports": [], "messages": [
                {"warning": {"gene_warning_code": "ABOVE_SPECIES_TAXON"}}]})
        with self.mock_http(handler):
            result = await api.dataset_genes("39948", gene_id="830878")
        self.assertEqual(result["messages"][0]["warning"]["gene_warning_code"], "ABOVE_SPECIES_TAXON")

    async def test_genes_requires_symbol_or_id(self):
        with mock.patch("servers.datasets_mcp.api.get_json", side_effect=AssertionError("network call")):
            for kwargs in [{}, {"symbol": "FLC", "gene_id": "830878"}]:
                with self.subTest(kwargs=kwargs), self.assertRaises(ValueError):
                    await api.dataset_genes("3702", **kwargs)

    async def test_taxon_report(self):
        def handler(req):
            self.assertTrue(req.url.path.endswith("/taxonomy/taxon/3702/dataset_report"))
            return httpx.Response(200, json={"reports": [{"taxonomy": {
                "tax_id": 3702, "rank": "SPECIES",
                "current_scientific_name": {"name": "Arabidopsis thaliana"}},
                "children": []}], "total_count": 1})
        with self.mock_http(handler):
            result = await api.dataset_taxon("3702")
        self.assertEqual(result["report"]["taxonomy"]["rank"], "SPECIES")

    async def test_taxon_404_mapped(self):
        with self.assertRaises(ValueError) as ctx:
            with self.mock_http(lambda req: httpx.Response(404)):
                await api.dataset_taxon("cactus nonexistentus")
        self.assertIn("Unknown taxon", str(ctx.exception))

    async def test_validation_before_network(self):
        with mock.patch("servers.datasets_mcp.api.get_json", side_effect=AssertionError("network call")):
            cases = [(api.dataset_assemblies, {"taxon": "bad taxon!"}),
                     (api.dataset_assemblies, {"taxon": "3702", "source": "ensembl"}),
                     (api.dataset_assemblies, {"taxon": "3702", "level": "supercontig"}),
                     (api.dataset_assemblies, {"taxon": "3702", "limit": 0}),
                     (api.dataset_assemblies, {"taxon": "3702", "limit": 201}),
                     (api.dataset_assemblies, {"taxon": "3702", "offset": -1}),
                     (api.dataset_assembly, {"accession": "GCF_000001735"}),
                     (api.dataset_genes, {"taxon": "3702", "symbol": "bad symbol!"}),
                     (api.dataset_genes, {"taxon": "3702", "symbol": "FLC", "limit": 501}),
                     (api.dataset_taxon, {"taxon": ""})]
            for func, kwargs in cases:
                with self.subTest(tool=func.__name__, kwargs=kwargs), self.assertRaises(ValueError):
                    await func(**kwargs)

    async def test_assembly_payload_shape(self):
        with self.mock_http(lambda req: httpx.Response(200, json=genome_page([genome_report()]))):
            result = await api.dataset_assembly("GCA_000001735.2")
        self.assertEqual(json.dumps(result["report"]["organism"]["tax_id"]), "3702")
