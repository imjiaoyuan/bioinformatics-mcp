from unittest.mock import AsyncMock, patch

import httpx

from servers.mesh_mcp import api
from tests.helpers import HTTPTestCase

LOOKUP_URL = "/mesh/lookup/descriptor"
SPARQL_URL = "/mesh/sparql"

DESCRIPTOR_XML = b"""<?xml version="1.0"?>
<rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#"
         xmlns:j.0="http://id.nlm.nih.gov/mesh/vocab#"
         xmlns:rdfs="http://www.w3.org/2000/01/rdf-schema#">
  <j.0:TopicalDescriptor rdf:about="http://id.nlm.nih.gov/mesh/D009369">
    <rdf:type rdf:resource="http://id.nlm.nih.gov/mesh/vocab#TopicalDescriptor"/>
    <j.0:active rdf:datatype="http://www.w3.org/2001/XMLSchema#boolean">true</j.0:active>
    <j.0:treeNumber rdf:resource="http://id.nlm.nih.gov/mesh/C04"/>
    <j.0:allowableQualifier rdf:resource="http://id.nlm.nih.gov/mesh/Q000639"/>
    <j.0:preferredTerm rdf:resource="http://id.nlm.nih.gov/mesh/T027926"/>
    <rdfs:label xml:lang="en">Neoplasms</rdfs:label>
    <j.0:considerAlso>consider also terms at CANCER, CARCINO-, ONCO-, and TUMOR</j.0:considerAlso>
  </j.0:TopicalDescriptor>
</rdf:RDF>
"""

QUALIFIER_XML = b"""<?xml version="1.0"?>
<rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#"
         xmlns:j.0="http://id.nlm.nih.gov/mesh/vocab#"
         xmlns:rdfs="http://www.w3.org/2000/01/rdf-schema#">
  <j.0:Qualifier rdf:about="http://id.nlm.nih.gov/mesh/Q000639">
    <j.0:broaderQualifier rdf:resource="http://id.nlm.nih.gov/mesh/Q000458"/>
    <rdfs:label xml:lang="en">trends</rdfs:label>
  </j.0:Qualifier>
</rdf:RDF>
"""

SCR_XML = b"""<?xml version="1.0"?>
<rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#"
         xmlns:j.0="http://id.nlm.nih.gov/mesh/vocab#"
         xmlns:rdfs="http://www.w3.org/2000/01/rdf-schema#">
  <j.0:SCR_Chemical rdf:about="http://id.nlm.nih.gov/mesh/C037656">
    <j.0:dateIntroduced rdf:datatype="http://www.w3.org/2001/XMLSchema#date">1995-01-01</j.0:dateIntroduced>
    <rdfs:label xml:lang="en">silymarin</rdfs:label>
  </j.0:SCR_Chemical>
</rdf:RDF>
"""

EMPTY_XML = b"""<?xml version="1.0"?>
<rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#">
</rdf:RDF>
"""


def _sparql_response(rows):
    return {"head": {"vars": sorted({key for row in rows for key in row})},
            "results": {"bindings": [{key: {"value": value} for key, value in row.items()}
                                     for row in rows]}}


class MeshTests(HTTPTestCase):
    def handler(self, tree_rows=()):
        def _handler(req):
            self.assertEqual(req.url.host, "id.nlm.nih.gov")
            if req.url.path == LOOKUP_URL:
                if req.url.params["label"] == "Neoplasms":
                    if req.url.params["match"] == "exact":
                        payload = [{"resource": "http://id.nlm.nih.gov/mesh/D009369",
                                    "label": "Neoplasms"}]
                    else:
                        payload = [{"resource": f"http://id.nlm.nih.gov/mesh/D0000{i}",
                                    "label": f"Neoplasm {i}"} for i in range(6)]
                else:
                    payload = []
                return httpx.Response(200, json=payload)
            if req.url.path == SPARQL_URL:
                return httpx.Response(200, json=_sparql_response(tree_rows))
            mesh_id = req.url.path.rsplit("/", 1)[-1]
            if mesh_id == "D009369":
                return httpx.Response(200, content=DESCRIPTOR_XML)
            if mesh_id == "Q000639":
                return httpx.Response(200, content=QUALIFIER_XML)
            if mesh_id == "C037656":
                return httpx.Response(200, content=SCR_XML)
            return httpx.Response(200, content=EMPTY_XML)
        return _handler

    async def test_lookup_exact_with_tree_numbers(self):
        rows = [{"d": "http://id.nlm.nih.gov/mesh/D009369", "code": "C04"}]
        with self.mock_http(self.handler(rows)), \
                patch("common.http.asyncio.sleep", new_callable=AsyncMock):
            lookup = await api.mesh_lookup("Neoplasms")
            self.assertEqual(lookup["source_url"],
                             "https://id.nlm.nih.gov/mesh/lookup/descriptor?label=Neoplasms&match=exact")
            self.assertEqual(lookup["results"], [
                {"mesh_id": "D009369", "label": "Neoplasms", "tree_numbers": ["C04"]}])
            self.assertEqual(lookup["total"], 1)
            self.assertEqual(lookup["pagination"], "local")

    async def test_lookup_contains_and_local_pagination(self):
        with self.mock_http(self.handler()), \
                patch("common.http.asyncio.sleep", new_callable=AsyncMock):
            page1 = await api.mesh_lookup("Neoplasms", match="contains", limit=4, offset=0)
            page2 = await api.mesh_lookup("Neoplasms", match="contains", limit=4, offset=4)
            self.assertEqual(page1["total"], 6)
            self.assertEqual([row["mesh_id"] for row in page1["results"]],
                             ["D00000", "D00001", "D00002", "D00003"])
            self.assertEqual([row["mesh_id"] for row in page2["results"]],
                             ["D00004", "D00005"])
            self.assertTrue(page2["truncated"] is False)

    async def test_lookup_empty_vs_error(self):
        with self.mock_http(self.handler()), \
                patch("common.http.asyncio.sleep", new_callable=AsyncMock):
            empty = await api.mesh_lookup("zzznope")
            self.assertEqual((empty["results"], empty["total"]), ([], 0))
        with self.mock_http(lambda req: httpx.Response(404)):
            with self.assertRaises(httpx.HTTPStatusError):
                await api.mesh_lookup("Neoplasms")

    async def test_entry_descriptor_qualifier_and_concept(self):
        with self.mock_http(self.handler()), \
                patch("common.http.asyncio.sleep", new_callable=AsyncMock):
            descriptor = await api.mesh_entry("d009369")
            self.assertEqual(descriptor["label"], "Neoplasms")
            self.assertEqual(descriptor["record_type"], "TopicalDescriptor")
            self.assertEqual(descriptor["tree_numbers"], ["C04"])
            self.assertEqual(descriptor["properties"]["allowableQualifier"],
                             ["http://id.nlm.nih.gov/mesh/Q000639"])
            qualifier = await api.mesh_entry("Q000639")
            self.assertEqual(qualifier["label"], "trends")
            concept = await api.mesh_entry("C037656")
            self.assertEqual(concept["record_type"], "SCR_Chemical")
            self.assertEqual(concept["properties"]["dateIntroduced"], ["1995-01-01"])
            self.assertEqual(concept["tree_numbers"], [])

    async def test_entry_unknown_id_is_valueerror(self):
        with self.mock_http(self.handler()), \
                patch("common.http.asyncio.sleep", new_callable=AsyncMock):
            with self.assertRaises(ValueError):
                await api.mesh_entry("C454422")

    async def test_tree_positions_and_pagination(self):
        rows = [{"root": "C04", "code": "C04", "parentCode": ""},
                {"root": "C04.588", "code": "C04.588", "parentCode": "C04"},
                {"root": "C04.588.180", "code": "C04.588.180", "parentCode": "C04.588"}]
        with self.mock_http(self.handler(rows)), \
                patch("common.http.asyncio.sleep", new_callable=AsyncMock):
            tree = await api.mesh_tree("D009369")
            self.assertEqual(tree["total"], 3)
            self.assertEqual(tree["results"][0]["position"], "C04")
            self.assertEqual(tree["results"][2]["parent"], "C04.588")
            self.assertEqual(tree["query_limit"], api.SPARQL_LIMIT)
            paged = await api.mesh_tree("D009369", limit=1, offset=1)
            self.assertEqual([row["position"] for row in paged["results"]], ["C04.588"])
            self.assertTrue(paged["pagination"] == "local" and paged["truncated"] is True)

    async def test_validation_before_any_request(self):
        mocks = [patch("common.api.request", new_callable=AsyncMock),
                 patch("servers.mesh_mcp.api.request", new_callable=AsyncMock)]
        with mocks[0] as api_mock, mocks[1] as http_mock:
            for func, args in [(api.mesh_lookup, {"label": ""}),
                               (api.mesh_lookup, {"label": "x" * 151}),
                               (api.mesh_lookup, {"label": "Neoplasms", "match": "prefix"}),
                               (api.mesh_lookup, {"label": "Neoplasms", "limit": 0}),
                               (api.mesh_lookup, {"label": "Neoplasms", "limit": 101}),
                               (api.mesh_lookup, {"label": "Neoplasms", "offset": -1}),
                               (api.mesh_entry, {"mesh_id": "D00936"}),
                               (api.mesh_entry, {"mesh_id": "X009369"}),
                               (api.mesh_tree, {"mesh_id": "C037656"}),
                               (api.mesh_tree, {"mesh_id": "D009369", "offset": 1_000_001})]:
                with self.subTest(tool=func.__name__, args=args), \
                        self.assertRaises(ValueError):
                    await func(**args)
            for mock in (api_mock, http_mock):
                mock.assert_not_called()