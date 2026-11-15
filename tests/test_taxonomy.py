from unittest.mock import AsyncMock, patch

import httpx

from servers.taxonomy_mcp import api
from tests.helpers import HTTPTestCase

TAXON_XML = """<?xml version="1.0"?>
<TaxaSet><Taxon>
    <TaxId>9606</TaxId>
    <ScientificName>Homo sapiens</ScientificName>
    <OtherNames><GenbankCommonName>human</GenbankCommonName></OtherNames>
    <Rank>species</Rank>
    <Division>Primates</Division>
    <Lineage>cellular organisms; Eukaryota; Opisthokonta; Metazoa</Lineage>
    <LineageEx>
        <Taxon><TaxId>131567</TaxId><ScientificName>cellular organisms</ScientificName><Rank>no rank</Rank></Taxon>
        <Taxon><TaxId>2759</TaxId><ScientificName>Eukaryota</ScientificName><Rank>superkingdom</Rank></Taxon>
        <Taxon><TaxId>9605</TaxId><ScientificName>Homo</ScientificName><Rank>genus</Rank></Taxon>
    </LineageEx>
    <CreateDate>1995/02/28</CreateDate>
    <UpdateDate>2024/09/10</UpdateDate>
</Taxon></TaxaSet>"""


def _esearch(uids, count=None):
    return {"esearchresult": {"count": str(count if count is not None else len(uids)),
                              "idlist": uids}}


def _esummary(uids, names):
    return {"result": {"uids": uids,
                       **{uid: {"taxid": uid, "scientificname": name, "rank": "species",
                                "division": "Primates", "status": "active",
                                "modificationdate": "2024/09/10 00:00"}
                          for uid, name in zip(uids, names)}}}


class TaxonomyTests(HTTPTestCase):
    async def test_ncbi_tools(self):
        calls = []

        def handler(req):
            calls.append((req.url.path, dict(req.url.params)))
            if req.url.path == "/entrez/eutils/esearch.fcgi":
                if req.url.params.get("term") == "Homo sapiens":
                    return httpx.Response(200, json=_esearch(["9606"], 1))
                if "Organism:exp" in req.url.params.get("term", ""):
                    return httpx.Response(200, json=_esearch(["741158", "63221", "9606", "9605"], 4))
            if req.url.path == "/entrez/eutils/esummary.fcgi":
                uids = req.url.params["id"].split(",")
                return httpx.Response(200, json=_esummary(uids, ["Homo sapiens"] * len(uids)))
            if req.url.path == "/entrez/eutils/efetch.fcgi":
                return httpx.Response(200, text=TAXON_XML)
            return httpx.Response(400, text="bad request")

        with self.mock_http(handler), patch("common.http.asyncio.sleep", new_callable=AsyncMock), \
                patch.dict("os.environ", {"NCBI_EMAIL": "researcher@example.org"}):
            lookup = await api.taxon_lookup("9606")
            self.assertEqual(lookup["taxid"], "9606")
            self.assertEqual(lookup["scientific_name"], "Homo sapiens")
            self.assertEqual(lookup["common_name"], "human")
            self.assertEqual(lookup["rank"], "species")
            self.assertEqual(lookup["lineage_summary"][-1],
                             {"taxid": "9605", "name": "Homo", "rank": "genus"})
            search = await api.taxon_search("Homo sapiens", limit=5)
            self.assertEqual(search["count"], 1)
            self.assertEqual(search["results"][0]["scientific_name"], "Homo sapiens")
            self.assertIn("eutils.ncbi.nlm.nih.gov", search["source_url"])
            children = await api.taxon_children("9605", limit=10)
            self.assertEqual(children["count"], 3)  # expansion count 4 minus the node itself
            self.assertEqual([row["taxid"] for row in children["results"]],
                             ["741158", "63221", "9606"])  # self excluded
            self.assertEqual(children["pagination"], "local")
            # paging maps to retstart/retmax upstream
            esearch_params = [params for path, params in calls
                              if path == "/entrez/eutils/esearch.fcgi"
                              and params.get("term") == "Homo sapiens"][0]
            self.assertEqual(esearch_params["retmax"], "5")
            self.assertEqual(esearch_params["retstart"], "0")

    async def test_ncbi_validation_and_errors(self):
        with self.mock_http(lambda req: httpx.Response(400, json={"error": "bad term"})), \
                patch("common.http.asyncio.sleep", new_callable=AsyncMock), \
                patch.dict("os.environ", {"NCBI_EMAIL": "researcher@example.org"}):
            with self.assertRaises(ValueError):
                await api.taxon_search("")
            with self.assertRaises(ValueError):
                await api.taxon_lookup("Homo")
            with self.assertRaises(ValueError):
                await api.taxon_children("9606; DROP", limit=5)
            with self.assertRaises(httpx.HTTPStatusError):
                await api.taxon_search("x[badfield]")

    async def test_ncbi_email_required(self):
        with self.mock_http(lambda req: httpx.Response(500)), \
                patch.dict("os.environ", {}, clear=True):
            with self.assertRaisesRegex(ValueError, "NCBI_EMAIL"):
                await api.taxon_lookup("9606")

    async def test_gbif_match(self):
        def handler(req):
            self.assertEqual(req.url.host, "api.gbif.org")
            if req.url.path == "/v1/species/match":
                if req.url.params["strict"] == "true":
                    return httpx.Response(200, json={"usageKey": 2436436, "matchType": "EXACT",
                                                     "scientificName": "Homo sapiens Linnaeus, 1758",
                                                     "canonicalName": "Homo sapiens",
                                                     "rank": "SPECIES", "status": "ACCEPTED",
                                                     "confidence": 99, "kingdom": "Animalia"})
                if req.url.params["name"].lower() == "homo sapiens":
                    return httpx.Response(200, json={"usageKey": 2436436, "matchType": "EXACT",
                                                     "scientificName": "Homo sapiens Linnaeus, 1758",
                                                     "canonicalName": "Homo sapiens", "rank": "SPECIES",
                                                     "status": "ACCEPTED", "confidence": 99,
                                                     "kingdom": "Animalia", "genus": "Homo"})
                return httpx.Response(200, json={"usageKey": None, "matchType": "NONE",
                                                 "scientificName": None, "confidence": 0})
            return httpx.Response(404)

        with self.mock_http(handler), patch("common.http.asyncio.sleep", new_callable=AsyncMock):
            match = await api.taxon_gbif_match("Homo sapiens")
            self.assertEqual(match["usage_key"], 2436436)
            self.assertEqual(match["match_type"], "EXACT")
            self.assertEqual(match["confidence"], 99)
            strict = await api.taxon_gbif_match("Homo sapiens", strict=True)
            self.assertEqual(strict["rank"], "SPECIES")
            none = await api.taxon_gbif_match("Not a species")
            self.assertEqual(none["match_type"], "NONE")
            self.assertIsNone(none["usage_key"])
            with self.assertRaises(ValueError):
                await api.taxon_gbif_match("")

    async def test_gbif_species_pagination(self):
        pages = {"first": False}

        def handler(req):
            self.assertEqual(req.url.host, "api.gbif.org")
            if req.url.path == "/v1/species/7707728":
                return httpx.Response(200, json={"key": 7707728, "scientificName": "Chordata",
                                                 "rank": "PHYLUM", "taxonomicStatus": "ACCEPTED",
                                                 "kingdom": "Animalia", "numDescendants": 3,
                                                 "vernacularNames": [{"vernacularName": "chordates"}],
                                                 "issues": []})
            if req.url.path == "/v1/species/7707728/children":
                offset = int(req.url.params["offset"])
                limit = int(req.url.params["limit"])
                self.assertEqual(limit, 100)
                if offset == 0:
                    pages["first"] = True
                    return httpx.Response(200, json={"offset": 0, "limit": limit,
                                                     "endOfRecords": False, "count": 3,
                                                     "results": [{"key": 359, "scientificName": "Mammalia",
                                                                  "rank": "CLASS", "taxonomicStatus": "ACCEPTED",
                                                                  "vernacularNames": [{"vernacularName": "mammals"}]}]})
                return httpx.Response(200, json={"offset": offset, "limit": limit,
                                                 "endOfRecords": True, "count": 3,
                                                 "results": [{"key": 1, "scientificName": "Aves",
                                                              "rank": "CLASS", "taxonomicStatus": "ACCEPTED",
                                                              "vernacularNames": []}]})
            return httpx.Response(404, json={"error": "not found"})

        with self.mock_http(handler), patch("common.http.asyncio.sleep", new_callable=AsyncMock):
            detail = await api.taxon_gbif_species(7707728, limit=1)
            self.assertTrue(pages["first"])
            self.assertEqual(detail["scientific_name"], "Chordata")
            self.assertEqual(detail["vernacular_names"], ["chordates"])
            constituents = detail["constituents"]
            self.assertEqual(constituents["pagination"], "local")
            self.assertEqual(constituents["total"], 2)
            self.assertEqual(constituents["results"][0]["key"], 359)
            self.assertEqual(constituents["results"][0]["vernacular_names"], ["mammals"])
            page2 = await api.taxon_gbif_species(7707728, limit=1, offset=1)
            self.assertEqual(page2["constituents"]["results"][0]["key"], 1)
            with self.assertRaises(ValueError):
                await api.taxon_gbif_species(0)

    async def test_gbif_species_unknown_key(self):
        with self.mock_http(lambda req: httpx.Response(404, json={"error": "no usage"})), \
                patch("common.http.asyncio.sleep", new_callable=AsyncMock):
            with self.assertRaises(ValueError):
                await api.taxon_gbif_species(999999999999999999)


class TaxonXmlUnitTests(HTTPTestCase):
    def test_parse_taxon_requires_record(self):
        with self.assertRaises(RuntimeError):
            api._parse_taxon("<TaxaSet></TaxaSet>")
        data = api._parse_taxon(TAXON_XML)
        self.assertEqual(len(data["lineage_summary"]), 3)
        self.assertEqual(data["division"], "Primates")

