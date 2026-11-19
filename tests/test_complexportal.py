"""Mocked tests for the Complex Portal MCP api."""
import httpx

from servers.complexportal_mcp import api
from tests.helpers import HTTPTestCase

SEARCH = {"size": 2, "totalNumberOfResults": 6, "elements": [
    {"complexAC": "CPX-26539", "complexName": "COP9 signalosome complex",
     "organismName": "Schizosaccharomyces pombe", "description": "Ubiquitin regulator"},
    {"complexAC": "CPX-1041", "complexName": "DASH/Dam1 complex", "organismName": "Saccharomyces cerevisiae"}]}
DETAILS = {"complexAc": "CPX-1041", "name": "DASH/Dam1 complex",
           "systematicName": "ASK1:DAD1:DAD2", "functions": ["kinetochore component"],
           "participants": [{"identifier": "P69852", "name": "HSK3", "stochiometry": "minValue: 1, maxValue: 1",
                             "interactorAC": "EBI-1379988", "bioRole": "unspecified role"}],
           "crossReferences": [{"database": "GO", "identifier": "GO:0000940"}]}


class ComplexPortalTests(HTTPTestCase):
    async def test_search_details_and_participants(self):
        paths = []

        def handler(req):
            paths.append((req.url.path, dict(req.url.params)))
            if req.url.path.endswith("/search/UBL"):
                self.assertEqual(req.url.params["first"], "10")
                self.assertEqual(req.url.params["number"], "5")
                return httpx.Response(200, json=SEARCH)
            if req.url.path.endswith("/complex/CPX-1041"):
                return httpx.Response(200, json=DETAILS)
            raise AssertionError(f"unexpected path: {req.url.path}")

        with self.mock_http(handler):
            search = await api.complexportal_search("UBL", limit=5, offset=10)
            self.assertEqual(search["totalNumberOfResults"], 6)
            self.assertEqual(search["elements"][0]["complexAC"], "CPX-26539")
            details = await api.complexportal_details("cpx-1041")
            self.assertEqual(details["systematicName"], "ASK1:DAD1:DAD2")
            self.assertIn("https://www.ebi.ac.uk/intact/complex-ws/complex/CPX-1041", details["source_url"])
            participants = await api.complexportal_participants("CPX-1041")
            self.assertEqual(participants["complex_ac"], "CPX-1041")
            self.assertEqual(participants["participants"][0]["identifier"], "P69852")
        self.assertEqual(len(paths), 3)

    async def test_validation_before_network(self):
        cases = [(api.complexportal_search, {"query": "", "limit": 1}),
                 (api.complexportal_search, {"query": "UBL", "limit": 0}),
                 (api.complexportal_search, {"query": "UBL", "offset": -1}),
                 (api.complexportal_search, {"query": "bad\nquery", "limit": 1}),
                 (api.complexportal_search, {"query": "x" * 301, "limit": 1}),
                 (api.complexportal_details, {"complex_ac": "UBL"}),
                 (api.complexportal_details, {"complex_ac": "CPX/1041"}),
                 (api.complexportal_participants, {"complex_ac": "EBI-4486632"})]
        for func, kwargs in cases:
            with self.subTest(tool=func.__name__, kwargs=kwargs), self.assertRaises(ValueError):
                await func(**kwargs)

    async def test_api_error(self):
        with self.mock_http(lambda req: httpx.Response(404)):
            with self.assertRaises(httpx.HTTPStatusError):
                await api.complexportal_details("CPX-99999999")
