"""Mocked tests for the OmniPath MCP api."""
import httpx

from servers.omnipath_mcp import api
from tests.helpers import HTTPTestCase

INTERACTIONS = [
    {"source": "P04637", "target": "O43663", "source_genesymbol": "TP53", "target_genesymbol": "PRC1",
     "is_directed": True, "is_stimulation": False, "is_inhibition": True, "consensus_direction": True,
     "consensus_stimulation": False, "consensus_inhibition": True, "sources": "CollecTRI;PhosphoSite",
     "references": "PMID:10458162", "type": "post_translational"},
    {"source": "P04638", "target": "P04637", "source_genesymbol": "EGFR", "target_genesymbol": "TP53",
     "is_directed": True, "is_stimulation": True, "is_inhibition": False, "consensus_direction": True,
     "consensus_stimulation": True, "consensus_inhibition": False, "sources": "SignaLink3",
     "references": "PMID:11997436", "type": "post_translational"}]
ENZSUB = [{"enzyme": "P50613", "substrate": "P04637", "residue_type": "S",
           "residue_offset": 33, "modification": "phosphorylation"}]
COMPLEXES = [{"name": "p300-MDM2-p53 protein complex", "components": ["P04637", "Q00987", "Q09472"],
              "components_genesymbols": ["EP300", "MDM2", "TP53"], "stoichiometry": "1:1:1",
              "sources": "CORUM", "references": "", "identifiers": {}}]
ANNOTATIONS = [{"uniprot": "P04637", "genesymbol": "TP53", "entity_type": "protein",
                "source": "CollecTRI", "label": "tf_type", "value": "dbTF", "record_id": 55}]


class OmniPathTests(HTTPTestCase):
    async def test_all_four_queries(self):
        seen = []

        def handler(req):
            seen.append((req.url.path, dict(req.url.params)))
            if req.url.path.endswith("/interactions/"):
                self.assertEqual(req.url.params["partners"], "P04637,P04638")
                self.assertEqual(req.url.params["organisms"], "9606")
                self.assertEqual(req.url.params["genesymbols"], "yes")
                self.assertIn("references", req.url.params["fields"])
                return httpx.Response(200, json=INTERACTIONS)
            if req.url.path.endswith("/enz_sub/"):
                self.assertEqual(req.url.params["substrates"], "P04637")
                self.assertNotIn("enzymes", req.url.params)
                return httpx.Response(200, json=ENZSUB)
            if req.url.path.endswith("/complexes/"):
                self.assertEqual(req.url.params["proteins"], "P04637,Q00987")
                return httpx.Response(200, json=COMPLEXES)
            if req.url.path.endswith("/annotations/"):
                self.assertEqual(req.url.params["proteins"], "TP53")
                return httpx.Response(200, json=ANNOTATIONS)
            raise AssertionError(f"unexpected path: {req.url.path}")

        with self.mock_http(handler):
            interactions = await api.omnipath_interactions(["P04637", "P04638"], limit=1)
            self.assertEqual(interactions["results"][0]["type"], "post_translational")
            self.assertEqual(interactions["total"], 2)
            self.assertTrue(interactions["truncated"])
            enzsub = await api.omnipath_enzyme_substrate(substrate="P04637")
            self.assertEqual(enzsub["results"][0]["modification"], "phosphorylation")
            complexes = await api.omnipath_complexes(["P04637", "Q00987"])
            self.assertEqual(complexes["results"][0]["components_genesymbols"], ["EP300", "MDM2", "TP53"])
            annotations = await api.omnipath_annotations(["TP53"])
            self.assertEqual(annotations["results"][0]["value"], "dbTF")
        self.assertEqual(len(seen), 4)

    async def test_validation_before_network(self):
        cases = [(api.omnipath_interactions, {"proteins": []}),
                 (api.omnipath_interactions, {"proteins": ["P04637"] * 11}),
                 (api.omnipath_interactions, {"proteins": ["TP53"], "limit": 0}),
                 (api.omnipath_interactions, {"proteins": ["TP53"], "organisms": 0}),
                 (api.omnipath_enzyme_substrate, {}),
                 (api.omnipath_enzyme_substrate, {"enzyme": ""}),
                 (api.omnipath_enzyme_substrate, {"enzyme": "TP53", "limit": -1}),
                 (api.omnipath_complexes, {"proteins": []}),
                 (api.omnipath_annotations, {"proteins": [""]})]
        for func, kwargs in cases:
            with self.subTest(tool=func.__name__, kwargs=kwargs), self.assertRaises(ValueError):
                await func(**kwargs)

    async def test_api_error(self):
        with self.mock_http(lambda req: httpx.Response(429)):
            with self.assertRaises(httpx.HTTPStatusError):
                await api.omnipath_annotations(["TP53"])
