import json
from unittest.mock import AsyncMock, patch

import httpx

from servers.opentargets_mcp import server
from tests.helpers import HTTPTestCase

TARGET = "ENSG00000141510"
DISEASE = "EFO_0000311"


class OpenTargetsTests(HTTPTestCase):
    async def test_typed_queries_variables_and_versions(self):
        queries = []
        def handler(req):
            self.assertEqual(req.method, "POST")
            body = json.loads(req.content)
            queries.append(body)
            self.assertIn("dataVersion", body["query"])
            return httpx.Response(200, json={"data": {"meta": {"dataVersion": {"year": "2026", "month": "09"}}, "target": {"id": TARGET}}})
        with self.mock_http(handler), patch("common.http.asyncio.sleep", new_callable=AsyncMock):
            calls = [server.opentargets_search('p53 " test'), server.opentargets_target(TARGET),
                     server.opentargets_disease(DISEASE), server.opentargets_associations(target_id=TARGET, limit=1, page=2),
                     server.opentargets_associations(disease_id=DISEASE), server.opentargets_drug("CHEMBL25"),
                     server.opentargets_evidence(TARGET, DISEASE, cursor="opaque")]
            for call in calls:
                result = await call
                self.assertEqual(result["status"], "ok")
                self.assertEqual(result["data"]["meta"]["dataVersion"]["month"], "09")
        self.assertNotIn('p53 " test', queries[0]["query"])
        self.assertEqual(queries[0]["variables"]["query"], 'p53 " test')
        self.assertEqual(queries[3]["variables"]["page"], {"size": 1, "index": 2})
        self.assertIn("maximumClinicalStage", queries[5]["query"])
        self.assertEqual(queries[-1]["variables"]["cursor"], "opaque")

    async def test_graphql_errors_partial_and_missing_entity(self):
        for data, status in [({"errors": [{"message": "schema error"}]}, "error"),
                             ({"data": {"target": None}, "errors": [{"message": "timeout"}]}, "partial"),
                             ({"data": {"target": None}}, "ok")]:
            with self.mock_http(lambda req: httpx.Response(200, json=data)):
                result = await server.opentargets_target(TARGET)
                self.assertEqual(result["status"], status)
                self.assertEqual(result["errors"], data.get("errors", []))

    async def test_validation_all_tools(self):
        for func, args in [(server.opentargets_search, {"query": ""}),
                           (server.opentargets_target, {"target_id": "TP53"}),
                           (server.opentargets_disease, {"disease_id": "bad"}),
                           (server.opentargets_associations, {"target_id": TARGET, "disease_id": DISEASE}),
                           (server.opentargets_drug, {"chembl_id": "../"}),
                           (server.opentargets_evidence, {"target_id": TARGET, "disease_id": DISEASE, "limit": 101})]:
            with self.subTest(tool=func.__name__), self.assertRaises(ValueError):
                await func(**args)

    async def test_retry_service_failure(self):
        calls = []
        def handler(req):
            calls.append(req)
            return httpx.Response(503) if len(calls) == 1 else httpx.Response(200, json={"data": {"target": None}})
        with self.mock_http(handler), patch("common.http.asyncio.sleep", new_callable=AsyncMock):
            self.assertEqual((await server.opentargets_target(TARGET))["status"], "ok")
        self.assertEqual(len(calls), 2)
