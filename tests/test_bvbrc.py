"""Mocked tests for the BV-BRC MCP api."""
import httpx

from servers.bvbrc_mcp import api
from tests.helpers import HTTPTestCase

SEARCH = [{"genome_id": "208224.13", "genome_name": "Mycolicibacterium tuberculosis H37Rv",
           "species": "Mycobacterium tuberculosis", "taxon_id": "83332", "genome_status": "Complete",
           "assembly_accession": "GCF_000195955.2", "bioproject_accession": "PRJNA218840",
           "cds": 3995, "genome_length": 4411532, "strain": "H37Rv"},
          {"genome_id": "83333.12", "genome_name": "Escherichia coli K-12 MG1655"}]
GENOME = [{"genome_id": "208224.13", "genome_name": "Mycolicibacterium tuberculosis H37Rv",
           "taxon_id": "83332", "genome_status": "Complete"}]
FEATURES = [{"feature_id": "fig|208224.13.peg.1", "genome_id": "208224.13",
             "genome_name": "M. tuberculosis H37Rv", "feature_type": "CDS",
             "accession": "NC_000962.3", "start": 190, "end": 255, "strand": "+",
             "product": "chromosomal replication initiator", "aa_length": 21,
             "na_length": 66, "go": ["GO:0006270", "GO:0003677"]}]


class BvbrcTests(HTTPTestCase):
    async def test_search_genome_and_features(self):
        seen = []

        def handler(req):
            seen.append(str(req.url))
            if "keyword(genome_name," in req.url.raw_path.decode():
                self.assertIn("tuberculosis", req.url.raw_path.decode())
                return httpx.Response(200, json=SEARCH)
            if "eq(genome_id,208224.13)" in req.url.raw_path.decode() and "genome_feature" not in req.url.raw_path.decode():
                return httpx.Response(200, json=GENOME)
            if req.url.path.startswith("/api/genome_feature/"):
                self.assertIn("limit(1)", req.url.raw_path.decode())
                return httpx.Response(200, json=FEATURES)
            raise AssertionError(f"unexpected URL: {req.url}")

        with self.mock_http(handler):
            search = await api.bvbrc_genome_search("tuberculosis", limit=1)
            self.assertEqual(search["results"][0]["genome_id"], "208224.13")
            self.assertEqual(search["total"], 2)
            self.assertTrue(search["truncated"])
            genome = await api.bvbrc_genome("208224.13")
            self.assertEqual(genome["genome_status"], "Complete")
            features = await api.bvbrc_features("208224.13", limit=1)
            self.assertEqual(features["results"][0]["product"], "chromosomal replication initiator")
            self.assertEqual(features["results"][0]["go"], ["GO:0006270", "GO:0003677"])
        self.assertEqual(len(seen), 3)

    async def test_missing_genome_is_an_error(self):
        with self.mock_http(lambda req: httpx.Response(200, json=[])):
            with self.assertRaises(ValueError):
                await api.bvbrc_genome("999999.99")

    async def test_unexpected_payload_is_an_error(self):
        with self.mock_http(lambda req: httpx.Response(200, text="<html>error</html>")):
            with self.assertRaises(ValueError):
                await api.bvbrc_genome_search("tuberculosis")

    async def test_validation_before_network(self):
        cases = [(api.bvbrc_genome_search, {"query": ""}),
                 (api.bvbrc_genome_search, {"query": "tu(berculosis)"}),
                 (api.bvbrc_genome_search, {"query": "tuberculosis; drop"}),
                 (api.bvbrc_genome_search, {"query": "tuberculosis", "limit": 0}),
                 (api.bvbrc_genome, {"genome_id": "208224"}),
                 (api.bvbrc_genome, {"genome_id": "E_coli"}),
                 (api.bvbrc_features, {"genome_id": "208224.13", "limit": 0}),
                 (api.bvbrc_features, {"genome_id": "208224.13", "offset": 950, "limit": 100})]
        for func, kwargs in cases:
            with self.subTest(tool=func.__name__, kwargs=kwargs), self.assertRaises(ValueError):
                await func(**kwargs)

    async def test_api_error(self):
        with self.mock_http(lambda req: httpx.Response(500)):
            with self.assertRaises(httpx.HTTPStatusError):
                await api.bvbrc_genome("208224.13")
