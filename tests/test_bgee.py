import httpx
from unittest.mock import AsyncMock, patch

from servers.bgee_mcp import server
from tests.helpers import HTTPTestCase


def sparql_results(variables, bindings):
    return {"head": {"vars": variables},
            "results": {"bindings": [{k: {"type": "literal", "value": v} for k, v in row.items()}
                                     for row in bindings]}}


def sent_query(calls):
    return calls[-1].params["query"]


class BgeeTests(HTTPTestCase):
    async def test_all_tools_success(self):
        calls = []
        results = {
            "?species ?scientificName ?commonName":
                sparql_results(["species", "scientificName", "commonName"],
                               [{"species": "http://purl.uniprot.org/taxonomy/9606",
                                 "scientificName": "Homo sapiens", "commonName": "human"}]),
            "?symbol ?description ?id ?organism ?uniprot ?ensembl ?ncbi":
                sparql_results(["symbol", "description", "id"],
                               [{"symbol": "APOC1", "description": "apolipoprotein C-I",
                                 "id": "ENSG00000130208"}]),
            "?geneName ?scientificName":
                sparql_results(["geneName", "scientificName"],
                               [{"geneName": "Mt-co1", "scientificName": "Mus musculus"}]),
            "?geneName ?anat ?anatName":
                sparql_results(["geneName", "anat", "anatName"],
                               [{"geneName": "APOC1", "anat": "http://purl.obolibrary.org/obo/UBERON_0000178",
                                 "anatName": "blood"}]),
            "?geneName ?anat ?anatName ?stage ?stageName ?score":
                sparql_results(["geneName", "anatName", "stageName", "score"],
                               [{"geneName": "APOC1", "anatName": "liver",
                                 "stageName": "post-juvenile", "score": "45.5"}]),
        }

        def handler(req):
            calls.append(req.url)
            if req.url.params["format"] != "application/sparql-results+json":
                raise AssertionError("missing SPARQL JSON format parameter")
            query = req.url.params["query"]
            select = query.split("SELECT DISTINCT ", 1)[1].split(" WHERE", 1)[0]
            if select in results:
                return httpx.Response(200, json=results[select])
            raise AssertionError(f"unexpected query: {query}")

        with self.mock_http(handler), patch("common.http.asyncio.sleep", new_callable=AsyncMock):
            self.assertEqual((await server.bgee_species(limit=5))["results"][0]["scientificName"], "Homo sapiens")
            info = await server.bgee_gene_info("ensg00000130208")
            self.assertEqual(info["results"][0]["id"], "ENSG00000130208")
            self.assertEqual((await server.bgee_gene_species("Mt-Co1"))["results"][0]["geneName"], "Mt-co1")
            expression = await server.bgee_gene_expression("APOC1", species="human", offset=10)
            self.assertEqual(expression["results"][0]["anatName"], "blood")
            scores = await server.bgee_gene_expression_scores("APOC1", species="Mouse")
            self.assertEqual(scores["results"][0]["score"], "45.5")
            genes = await server.bgee_anatomy_genes("Brain", limit=2)
            self.assertEqual(genes["limit"], 2)
        self.assertEqual(len(calls), 6)
        for call in calls:
            self.assertIn("https://www.bgee.org/sparql?", str(call))
        self.assertIn('LCASE(?geneName) = "apoc1"', sent_query(calls[3:4]))
        self.assertIn('LCASE(?spName) = "mouse"', sent_query(calls[4:5]))
        self.assertIn('LCASE(?anatName) = "brain"', sent_query(calls[5:6]))
        self.assertIn("LIMIT 5", sent_query(calls[0:1]))
        self.assertIn("OFFSET 10", sent_query(calls[3:4]))
        self.assertIn('"ENSG00000130208"', sent_query(calls[1:2]))

    async def test_validation_all_tools(self):
        cases = [(server.bgee_species, {"limit": 0}), (server.bgee_species, {"offset": -1}),
                 (server.bgee_gene_info, {"ensembl_id": "bad"}), (server.bgee_gene_species, {"gene": "a; DROP"}),
                 (server.bgee_gene_expression, {"gene": "APOC1", "species": "hu*man"}),
                 (server.bgee_gene_expression_scores, {"gene": "", "limit": 101}),
                 (server.bgee_anatomy_genes, {"anatomy": "brain\n"})]
        for func, kwargs in cases:
            with self.subTest(tool=func.__name__), self.assertRaises(ValueError):
                await func(**kwargs)

    async def test_api_error(self):
        with self.mock_http(lambda req: httpx.Response(404)):
            with self.assertRaises(httpx.HTTPStatusError):
                await server.bgee_gene_expression("APOC1")
