import json
from unittest.mock import AsyncMock, patch

import httpx

from servers.clinicaltrials_mcp import api
from tests.helpers import HTTPTestCase

NCT = "NCT00000111"


def study_body():
    return {
        "protocolSection": {
            "identificationModule": {"nctId": NCT, "briefTitle": "A Study",
                                     "organization": {"fullName": "NIH"}},
            "statusModule": {"overallStatus": "COMPLETED", "whyStopped": "done"},
            "sponsorCollaboratorsModule": {"leadSponsor": {"name": "NCRR"},
                                           "collaborators": [{"name": "NIH"}]},
            "designModule": {"phases": ["PHASE2"], "enrollmentInfo": {"count": 42},
                             "studyInfo": {"studyType": "INTERVENTIONAL",
                                           "primaryPurpose": "TREATMENT"}},
            "armsInterventionsModule": {
                "armGroups": [{"label": "Drug A", "type": "EXPERIMENTAL",
                               "interventions": [{"name": "Drug A"}]}],
                "interventions": [{"name": "Drug A", "type": "DRUG"}]},
            "eligibilityModule": {"sex": "ALL", "minimumAge": "18 Years",
                                  "maximumAge": "65 Years", "healthyVolunteers": False,
                                  "eligibilityCriteria": "Inclusion: adults"},
            "outcomesModule": {"primaryOutcomes": [{"measure": "Response rate", "timeFrame": "1 year"}],
                               "secondaryOutcomes": [{"measure": "Survival", "timeFrame": "5 years"}]},
        }
    }


class ClinicalTrialsTests(HTTPTestCase):
    async def test_search_request_params_and_response(self):
        requests = []
        def handler(req):
            requests.append(req)
            return httpx.Response(200, json={"studies": [{"protocolSection": {
                "identificationModule": {"nctId": NCT, "briefTitle": "A Study"},
                "statusModule": {"overallStatus": "COMPLETED"},
                "sponsorCollaboratorsModule": {"leadSponsor": {"name": "NCRR"}},
                "designModule": {"phases": ["PHASE2"], "enrollmentInfo": {"count": 42}}}}],
                "nextPageToken": "tok123"})
        with self.mock_http(handler), patch("common.http.asyncio.sleep", new_callable=AsyncMock):
            result = await api.trial_search(condition="asthma", status="recruiting",
                                            limit=5, cursor="prev")
        url = requests[0].url.params
        self.assertEqual(url["query.cond"], "asthma")
        self.assertEqual(url["filter.overallStatus"], "RECRUITING")
        self.assertEqual(url["pageSize"], "5")
        self.assertEqual(url["pageToken"], "prev")
        self.assertEqual(result["studies"][0]["nct_id"], NCT)
        self.assertEqual(result["next_cursor"], "tok123")
        self.assertTrue(result["has_more"])
        self.assertEqual(result["pagination"], "cursor")

    async def test_search_no_cursor_and_last_page(self):
        def handler(req):
            self.assertNotIn("pageToken", req.url.params)
            return httpx.Response(200, json={"studies": []})
        with self.mock_http(handler), patch("common.http.asyncio.sleep", new_callable=AsyncMock):
            result = await api.trial_search(term="asthma")
        self.assertEqual(result["studies"], [])
        self.assertIsNone(result["next_cursor"])
        self.assertFalse(result["has_more"])

    async def test_study_compact_fields_and_urls(self):
        def handler(req):
            self.assertTrue(req.url.path.endswith(f"/studies/{NCT}"))
            return httpx.Response(200, json=study_body())
        with self.mock_http(handler), patch("common.http.asyncio.sleep", new_callable=AsyncMock):
            result = await api.trial_study(NCT.lower())
        self.assertEqual(result["nct_id"], NCT)
        self.assertEqual(result["lead_sponsor"], "NCRR")
        self.assertEqual(result["collaborators"], ["NIH"])
        self.assertEqual(result["phases"], ["PHASE2"])
        self.assertEqual(result["enrollment"], 42)
        self.assertEqual(result["arms"][0]["label"], "Drug A")
        self.assertEqual(result["primary_outcomes"][0]["measure"], "Response rate")
        self.assertFalse(result["has_results"])
        self.assertEqual(result["study_url"], f"https://clinicaltrials.gov/study/{NCT}")
        self.assertEqual(result["source_url"], f"https://clinicaltrials.gov/api/v2/studies/{NCT}")

    async def test_study_with_results_section(self):
        body = study_body()
        body["resultsSection"] = {"participantFlowModule": {}}
        with self.mock_http(lambda req: httpx.Response(200, json=body)), \
                patch("common.http.asyncio.sleep", new_callable=AsyncMock):
            self.assertTrue((await api.trial_study(NCT))["has_results"])

    async def test_unknown_study_raises_http_error(self):
        with self.mock_http(lambda req: httpx.Response(404, json={"error": "not found"})), \
                patch("common.http.asyncio.sleep", new_callable=AsyncMock):
            with self.assertRaises(httpx.HTTPStatusError):
                await api.trial_study(NCT)

    async def test_early_validation_makes_no_request(self):
        request_mock = AsyncMock()
        with patch("common.http.request", request_mock):
            cases = [(api.trial_search, {}),
                     (api.trial_search, {"condition": "asthma", "limit": 101}),
                     (api.trial_search, {"condition": "asthma", "limit": 0}),
                     (api.trial_search, {"condition": "asthma", "status": "bogus"}),
                     (api.trial_search, {"condition": "asthma", "cursor": ""}),
                     (api.trial_search, {"condition": "asthma", "term": "x" * 2001}),
                     (api.trial_study, {"nct_id": "TP53"}),
                     (api.trial_study, {"nct_id": "NCT12345"}),
                     (api.trial_study, {"nct_id": ""})]
            for func, args in cases:
                with self.subTest(tool=func.__name__, args=args), self.assertRaises(ValueError):
                    await func(**args)
        request_mock.assert_not_called()

    async def test_cursor_chain_bounded_fetches(self):
        calls = []
        def handler(req):
            token = req.url.params.get("pageToken")
            calls.append(token)
            nct = {None: NCT, "HCT-FQ": "NCT11111111", "HCT-FQ2": "NCT22222222"}[token]
            body = {"studies": [{"protocolSection": {"identificationModule": {"nctId": nct}}}]}
            if token != "HCT-FQ2":
                body["nextPageToken"] = "HCT-FQ" if token is None else "HCT-FQ2"
            return httpx.Response(200, json=body)
        with self.mock_http(handler), patch("common.http.asyncio.sleep", new_callable=AsyncMock):
            first = await api.trial_search(condition="asthma", limit=1)
            self.assertEqual(calls[-1], None)
            second = await api.trial_search(condition="asthma", limit=1, cursor=first["next_cursor"])
            third = await api.trial_search(condition="asthma", limit=1, cursor=second["next_cursor"])
        self.assertEqual(calls, [None, "HCT-FQ", "HCT-FQ2"])
        self.assertEqual([first["studies"][0]["nct_id"], second["studies"][0]["nct_id"],
                          third["studies"][0]["nct_id"]], [NCT, "NCT11111111", "NCT22222222"])
        self.assertIsNone(third["next_cursor"])
