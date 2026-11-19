"""Mocked tests for the RxNorm MCP api."""
import httpx

from servers.rxnorm_mcp import api
from tests.helpers import HTTPTestCase

DRUGS = {"drugGroup": {"conceptGroup": [
    {"tty": "IN", "conceptProperties": [{"rxcui": "1191", "name": "Aspirin", "synonym": "aspirin",
                                         "tty": "IN", "suppress": "N", "umlscui": "", "language": "ENG"}]},
    {"tty": "SBD", "conceptProperties": [{"rxcui": "1141501", "name": "aspirin 81 MG Oral Tablet",
                                          "synonym": "", "tty": "SBD", "suppress": "N", "umlscui": ""}]}]}}
PROPERTIES = {"properties": {"rxcui": "1191", "name": "aspirin", "synonym": "", "tty": "IN",
                             "language": "ENG", "suppress": "N", "umlscui": ""}}
RELATED = {"relatedGroup": {"rxcui": "1191", "conceptGroup": [
    {"tty": "IN", "conceptProperties": [{"rxcui": "1191", "name": "aspirin", "synonym": "",
                                         "tty": "IN", "suppress": "N", "umlscui": ""}]}]}}


class RxNormTests(HTTPTestCase):
    async def test_drugs_properties_and_related(self):
        seen = []

        def handler(req):
            seen.append(req.url.path)
            if req.url.path.endswith("/drugs"):
                self.assertEqual(req.url.params["name"], "aspirin")
                return httpx.Response(200, json=DRUGS)
            if req.url.path.endswith("/rxcui/1191/properties"):
                return httpx.Response(200, json=PROPERTIES)
            if req.url.path.endswith("/rxcui/1191/related"):
                self.assertEqual(req.url.params["tty"], "SCD+SBD")
                return httpx.Response(200, json=RELATED)
            raise AssertionError(f"unexpected path: {req.url.path}")

        with self.mock_http(handler):
            drugs = await api.rxnorm_drugs("aspirin", limit=1)
            self.assertEqual(drugs["results"][0]["rxcui"], "1191")
            self.assertEqual(drugs["total"], 2)
            self.assertTrue(drugs["truncated"])
            self.assertEqual(drugs["pagination"], "local")
            properties = await api.rxnorm_properties("1191")
            self.assertEqual(properties["name"], "aspirin")
            self.assertEqual(properties["tty"], "IN")
            related = await api.rxnorm_related("1191", tty="SCD,SBD")
            self.assertEqual(related["total"], 1)
        self.assertEqual(len(seen), 3)

    async def test_missing_properties_are_an_error(self):
        with self.mock_http(lambda req: httpx.Response(200, json={})):
            with self.assertRaises(ValueError):
                await api.rxnorm_properties("999")

    async def test_validation_before_network(self):
        cases = [(api.rxnorm_drugs, {"name": ""}),
                 (api.rxnorm_drugs, {"name": "aspi\nrin"}),
                 (api.rxnorm_drugs, {"name": "aspirin", "limit": 0}),
                 (api.rxnorm_properties, {"rxcui": "1191a"}),
                 (api.rxnorm_related, {"rxcui": "bad", "tty": "IN"}),
                 (api.rxnorm_related, {"rxcui": "1191", "tty": "xyz"}),
                 (api.rxnorm_related, {"rxcui": "1191", "tty": "IN;PIN"})]
        for func, kwargs in cases:
            with self.subTest(tool=func.__name__, kwargs=kwargs), self.assertRaises(ValueError):
                await func(**kwargs)

    async def test_api_error(self):
        with self.mock_http(lambda req: httpx.Response(404, text="Not found")):
            with self.assertRaises(httpx.HTTPStatusError):
                await api.rxnorm_properties("999")
