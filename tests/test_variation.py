import json
import os
from unittest.mock import AsyncMock, patch

import httpx

from servers.variation_mcp import api
from tests.helpers import HTTPTestCase


def _variation(name="rs699"):
    return {"name": name, "most_severe_consequence": "missense_variant", "var_class": "SNP",
            "clinical_significance": ["benign"], "minor_allele": "G", "MAF": 0.2,
            "ambiguity": "R", "source": "dbSNP", "evidence": ["Frequency", "1000Genomes"],
            "synonyms": ["rs4714"],
            "mappings": [
                {"assembly_name": "GRCh38", "seq_region_name": "1", "start": 230710048,
                 "end": 230710048, "allele_string": "A/G", "strand": 1,
                 "location": "1:230710048-230710048"},
                {"assembly_name": "NCBI36", "seq_region_name": "1", "start": 230845794,
                 "end": 230845794, "allele_string": "A/G", "strand": 1,
                 "location": "1:230845794-230845794"}],
            "populations": [{"population": "1000GENOMES:phase_3:AFR", "pop_samplesize": 661,
                             "freqs": {"A": "0.1607", "G": "0.8393"}},
                            {"population": "1000GENOMES:phase_3:EUR", "pop_samplesize": 503,
                             "freqs": {"A": "0.4573", "G": "0.5427"}}]}


def _esearch(count=2, ids=None):
    return {"esearchresult": {"count": str(count), "idlist": ids if ids is not None
                              else ["699", "4714"]}}


def _esummary(uids):
    docsums = {"699": {"uid": "699", "snp_id": 699, "tax_id": "9606", "snp_class": "snv",
                       "allele_origin": "", "validated": "by-frequency,by-alfa",
                       "fxn_class": "coding_sequence_variant,missense_variant",
                       "genes": [{"name": "AGT", "gene_id": "183"}], "chr": "1",
                       "acc": "NC_000001.11", "chrpos": "1:230710048",
                       "spdi": "NC_000001.11:230710047:A:G",
                       "clinical_significance": "risk-factor,benign",
                       "map_weight": "2", "createdate": "2000/09/19", "updatedate": "2024/11/02"},
               "4714": {"uid": "4714", "snp_id": 4714, "tax_id": "9606", "snp_class": "snv",
                        "validated": "", "genes": [], "chr": "1", "acc": "NC_000001.11",
                        "chrpos": "1:230710048"}}
    return {"header": {"type": "esummary"}, "result": {"uids": uids,
                                                       **{uid: docsums[uid] for uid in uids if uid in docsums}}}


def _handler(self, requests):
    def handler(req):
        requests.append((req.url.host, req.url.path, dict(req.url.params)))
        if req.url.host == "rest.ensembl.org":
            name = req.url.path.rsplit("/", 1)[-1]
            if name == "rs404":
                return httpx.Response(404, json={"error": "ID not found"})
            if name == "rs500":
                return httpx.Response(500)
            return httpx.Response(200, json=_variation(name))
        if "esearch" in req.url.path:
            return httpx.Response(200, json=_esearch())
        uids = req.url.params["id"].split(",")
        return httpx.Response(200, json=_esummary(uids))
    return handler


class VariationTests(HTTPTestCase):
    async def test_variation_tools(self):
        requests = []

        def handler(req):
            requests.append(req.url.path)
            if req.url.path.endswith("/rs404"):
                return httpx.Response(404, json={"error": "ID not found"})
            return httpx.Response(200, json=_variation(req.url.path.rsplit("/", 1)[-1]))

        with self.mock_http(handler), patch("common.http.asyncio.sleep", new_callable=AsyncMock):
            entry = await api.variation_entry("699")
            self.assertEqual(entry["rsid"], "rs699")
            self.assertEqual(entry["most_severe_consequence"], "missense_variant")
            self.assertEqual(entry["clinical_significance"], ["benign"])
            self.assertEqual(entry["grch38_location"]["location"], "1:230710048-230710048")
            self.assertEqual(entry["mappings"][0]["assembly"], "GRCh38")
            self.assertIn("rest.ensembl.org", entry["source_url"])
            self.assertEqual(requests[-1], "/variation/human/rs699")

            pops = await api.variation_populations("RS699", limit=1, offset=1)
            self.assertEqual(pops["results"], [{"population": "1000GENOMES:phase_3:EUR",
                                                "sample_size": 503,
                                                "allele_frequencies": {"A": "0.4573", "G": "0.5427"}}])
            self.assertEqual((pops["total"], pops["limit"], pops["offset"], pops["pagination"]),
                             (2, 1, 1, "local"))
            self.assertFalse(pops["truncated"])

            batch = await api.variation_batch(["699", 4714, "404"], species="human")
            self.assertEqual([row["rsid"] for row in batch["entries"]], ["rs699", "rs4714"])
            self.assertIn("rs404", batch["errors"])
            self.assertTrue(batch["partial"])
            self.assertFalse(batch["all_failed"])

            all_bad = await api.variation_batch(["404"])
            self.assertTrue(all_bad["all_failed"] and all_bad["partial"])
        self.assertEqual(requests[-4:], ["/variation/human/rs699", "/variation/human/rs4714",
                                         "/variation/human/rs404", "/variation/human/rs404"])

    async def test_dbsnp_tools(self):
        requests = []

        with self.mock_http(_handler(self, requests)), \
                patch("common.http.asyncio.sleep", new_callable=AsyncMock), \
                patch.dict(os.environ, {"NCBI_EMAIL": "researcher@example.org"}):
            summary = await api.dbsnp_summary(["rs699", "4714"])
            self.assertEqual(summary["requested"], 2)
            self.assertEqual(summary["missing"], [])
            self.assertFalse(summary["partial"])
            row = summary["results"][0]
            self.assertEqual(row["organism"], "Homo sapiens")
            self.assertEqual(row["tax_id"], "9606")
            self.assertEqual(row["validated"], ["by-frequency", "by-alfa"])
            self.assertEqual(row["genes"], [{"symbol": "AGT", "gene_id": "183"}])
            self.assertEqual(row["position"], "1:230710048")
            self.assertEqual(row["mapweight"], "2")
            self.assertIn("eutils.ncbi.nlm.nih.gov", summary["source_url"])

            partial = await api.dbsnp_summary(["rs699", "rs9999999"])
            self.assertEqual(partial["missing"], ["rs9999999"])
            self.assertTrue(partial["partial"])
            self.assertEqual(len(partial["results"]), 1)

            search = await api.dbsnp_search("AGT[gene]", limit=2, offset=0)
            self.assertEqual(search["count"], 2)
            self.assertEqual(search["uids"], ["699", "4714"])
            self.assertEqual(search["limit"], 2)
        esummary = next(params for host, path, params in requests if "esummary" in path)
        self.assertEqual(esummary["email"], "researcher@example.org")
        self.assertEqual(esummary["db"], "snp")

    async def test_validation_all_tools(self):
        with self.mock_http(lambda req: httpx.Response(200, json=_variation())), \
                patch.dict(os.environ, {"NCBI_EMAIL": "researcher@example.org"}):
            for func, args in [(api.variation_entry, {"rsid": "rsxx123"}),
                               (api.variation_entry, {"rsid": "699", "species": "Homo Sapiens"}),
                               (api.variation_entry, {"rsid": "699", "species": "Homo Sapiens"}),
                               (api.variation_entry, {"rsid": ""}),
                               (api.variation_populations, {"rsid": "699", "limit": 0}),
                               (api.variation_populations, {"rsid": "699", "offset": -1}),
                               (api.variation_batch, {"rs_ids": []}),
                               (api.variation_batch, {"rs_ids": ["rs699"] * 21}),
                               (api.variation_batch, {"rs_ids": ["x" * 200]}),
                               (api.dbsnp_summary, {"rs_ids": []}),
                               (api.dbsnp_summary, {"rs_ids": ["notanrsid"]}),
                               (api.dbsnp_search, {"term": ""}),
                               (api.dbsnp_search, {"term": "x", "limit": 0})]:
                with self.subTest(tool=func.__name__), self.assertRaises(ValueError):
                    await func(**args)

    async def test_missing_ncbi_email(self):
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaises(ValueError) as ctx:
                await api.dbsnp_summary(["rs699"])
            self.assertIn("NCBI_EMAIL", str(ctx.exception))
            with self.assertRaises(ValueError):
                await api.dbsnp_search("AGT[gene]")

    async def test_ensembl_404(self):
        with self.mock_http(lambda req: httpx.Response(404, json={"error": "ID not found"})), \
                patch("common.http.asyncio.sleep", new_callable=AsyncMock):
            with self.assertRaises(httpx.HTTPStatusError):
                await api.variation_entry("rs699")

    async def test_rate_limit_retry(self):
        attempts = []

        def handler(req):
            attempts.append(req.url.path)
            if len(attempts) == 1:
                return httpx.Response(429, headers={"Retry-After": "0.01"})
            return httpx.Response(200, json=_variation())

        with self.mock_http(handler), patch("common.http.asyncio.sleep", new_callable=AsyncMock):
            entry = await api.variation_entry("rs699")
        self.assertEqual(entry["rsid"], "rs699")
        self.assertEqual(len(attempts), 2)
