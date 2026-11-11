import os
from unittest.mock import AsyncMock, patch

import httpx

from servers.clinvar_mcp import api
from tests.helpers import HTTPTestCase

ESUMMARY = {
    "header": {"type": "esummary", "version": "0.3"},
    "result": {"uids": ["5042478"], "5042478": {
        "uid": "5042478", "obj_type": "single nucleotide variant",
        "accession": "VCV005042478", "accession_version": "VCV005042478.1",
        "title": "NM_000059.4(BRCA2):c.1408G>T (p.Glu470Ter)",
        "variation_set": [{"measure_id": "5152756", "variation_name": "NM_000059.4(BRCA2):c.1408G>T",
                           "canonical_spdi": "NC_000013.11:32332885:G:T",
                           "variation_loc": [{"status": "current", "assembly_name": "GRCh38", "chr": "13",
                                              "start": "32332886", "stop": "32332886"}]}],
        "supporting_submissions": {"scv": ["SCV008144391"], "rcv": ["RCV007129667"]},
        "germline_classification": {"description": "Pathogenic", "last_evaluated": "2026/08/13 00:00",
                                    "review_status": "criteria provided, single submitter",
                                    "trait_set": [{"trait_name": "Breast-ovarian cancer, familial, susceptibility to, 2"}]},
        "genes": [{"symbol": "BRCA2", "geneid": "675"}],
        "molecular_consequence_list": ["nonsense"], "protein_change": "E470*"},
        "5042473": {"uid": "5042473", "obj_type": "single nucleotide variant",
                    "accession": "VCV005042473", "title": "NM_000059.4(BRCA2):c.1408G>C"}},
}

RCV_XML = """<?xml version="1.0" encoding="UTF-8"?>
<ClinVarResult-Set><ClinVarSet ID="320016743">
  <RecordStatus>current</RecordStatus>
  <Title>NM_000059.4(BRCA2):c.1408G&gt;T (p.Glu470Ter) AND Breast-ovarian cancer</Title>
  <ReferenceClinVarAssertion ID="15487398">
    <ClinVarAccession Acc="RCV007129667" Version="1" Type="RCV"/>
    <RecordStatus>current</RecordStatus>
    <Classifications>
      <GermlineClassification>
        <ReviewStatus>criteria provided, single submitter</ReviewStatus>
        <Description DateLastEvaluated="2026-08-13">Pathogenic</Description>
      </GermlineClassification>
    </Classifications>
    <MeasureSet Type="Variant" ID="5042478" Acc="VCV005042478" Version="1">
      <Measure Type="single nucleotide variant" ID="5152756">
        <Name><ElementValue Type="Preferred">NM_000059.4(BRCA2):c.1408G&gt;T (p.Glu470Ter)</ElementValue></Name>
        <AttributeSet><Attribute Accession="NM_000059" Version="4" Change="c.1408G&gt;T" Type="HGVS, coding, RefSeq">NM_000059.4:c.1408G&gt;T</Attribute></AttributeSet>
        <AttributeSet><Attribute Accession="NP_000050" Version="2" Change="p.Glu470Ter" Type="HGVS, protein">NP_000050.2:p.Glu470Ter</Attribute></AttributeSet>
        <MeasureRelationship Type="within single gene">
          <Name><ElementValue Type="Preferred">BRCA2 DNA repair associated</ElementValue></Name>
          <Symbol><ElementValue Type="Preferred">BRCA2</ElementValue></Symbol>
        </MeasureRelationship>
      </Measure>
    </MeasureSet>
    <TraitSet Type="Disease" ID="2560">
      <Trait ID="636" Type="Disease">
        <Name><ElementValue Type="Preferred">Breast-ovarian cancer, familial, susceptibility to, 2</ElementValue>
        <XRef ID="MONDO:0012933" DB="MONDO"/></Name>
        <XRef ID="C2675520" DB="MedGen"/>
      </Trait>
    </TraitSet>
  </ReferenceClinVarAssertion>
  <ClinVarAssertion ID="15486240">
    <ClinVarSubmissionID localKey="100415395|OMIM:612555" submitter="Myriad Genetics, Inc."/>
    <ClinVarAccession Acc="SCV008144391" Version="1" Type="SCV" OrgID="507240"/>
    <RecordStatus>current</RecordStatus>
    <Classification DateLastEvaluated="2026-08-13">
      <ReviewStatus>criteria provided, single submitter</ReviewStatus>
      <GermlineClassification>Pathogenic</GermlineClassification>
      <Comment Type="public">Premature protein truncation.</Comment>
    </Classification>
    <ObservedIn><Method><MethodType>clinical testing</MethodType></Method></ObservedIn>
  </ClinVarAssertion>
</ClinVarSet></ClinVarResult-Set>"""


class ClinVarTests(HTTPTestCase):
    def setUp(self):
        super().setUp()
        environ = patch.dict(os.environ, {"NCBI_EMAIL": "researcher@example.org"})
        environ.start()
        self.addCleanup(environ.stop)

    async def test_search_variant_and_variants(self):
        def handler(req):
            if "esearch" in req.url.path:
                self.assertEqual(req.url.params["term"], "BRCA2[gene]")
                self.assertEqual(req.url.params["retmax"], "5")
                self.assertEqual(req.url.params["retstart"], "2")
                self.assertNotIn("limit", req.url.params)
                self.assertNotIn("offset", req.url.params)
                self.assertEqual(req.url.params["tool"], "clinvar-mcp")
                return httpx.Response(200, json={"esearchresult": {"count": "3", "idlist": ["5042478"]}})
            self.assertIn("5042478", req.url.params["id"].split(","))
            return httpx.Response(200, json=ESUMMARY)
        with self.mock_http(handler), patch("common.http.asyncio.sleep", new_callable=AsyncMock):
            search = await api.clinvar_search("BRCA2[gene]", limit=5, offset=2)
            self.assertEqual(search["count"], 3)
            self.assertEqual(search["uids"], ["5042478"])
            self.assertIn("source_url", search)
            variant = await api.clinvar_variant("5042478")
            self.assertEqual(variant["accession"], "VCV005042478")
            self.assertEqual(variant["genes"], ["BRCA2"])
            self.assertEqual(variant["germline_classification"]["description"], "Pathogenic")
            self.assertEqual(variant["germline_classification"]["review_status"],
                             "criteria provided, single submitter")
            self.assertEqual(variant["locations"][0]["assembly"], "GRCh38")
            self.assertEqual(variant["spdi"], "NC_000013.11:32332885:G:T")
            self.assertEqual(variant["submissions"]["rcv"], ["RCV007129667"])
            self.assertEqual(variant["protein_change"], "E470*")
            batch = await api.clinvar_variants(["5042478", "5042473"], limit=1, offset=1)
            self.assertEqual(batch["pagination"], "local")
            self.assertEqual(batch["total"], 2)
            self.assertEqual(batch["results"][0]["uid"], "5042473")
            self.assertFalse(batch["truncated"])

    async def test_vcv_accession_lookup(self):
        def handler(req):
            if "esearch" in req.url.path:
                return httpx.Response(200, json={"esearchresult": {"count": "1", "idlist": ["5042478"]}})
            return httpx.Response(200, json=ESUMMARY)
        with self.mock_http(handler), patch("common.http.asyncio.sleep", new_callable=AsyncMock):
            self.assertEqual((await api.clinvar_variant("VCV005042478"))["uid"], "5042478")

    async def test_rcv_record(self):
        def handler(req):
            self.assertEqual(req.url.params["id"], "RCV007129667")
            self.assertEqual(req.url.params["rettype"], "clinvarset")
            self.assertEqual(req.url.params["retmode"], "xml")
            return httpx.Response(200, content=RCV_XML.encode())
        with self.mock_http(handler), patch("common.http.asyncio.sleep", new_callable=AsyncMock):
            record = await api.clinvar_rcv("rcv007129667")
            self.assertEqual(record["rcv_accession"], "RCV007129667")
            self.assertEqual(record["germline_classification"], "Pathogenic")
            self.assertEqual(record["review_status"], "criteria provided, single submitter")
            self.assertEqual(record["trait"]["name"],
                             "Breast-ovarian cancer, familial, susceptibility to, 2")
            self.assertEqual(record["variant"]["vcv_accession"], "VCV005042478")
            self.assertEqual(record["variant"]["gene"]["symbol"], "BRCA2")
            self.assertEqual(record["variant"]["hgvs"],
                             ["NM_000059.4:c.1408G>T", "NP_000050.2:p.Glu470Ter"])
            submission = record["submissions"][0]
            self.assertEqual(submission["scv_accession"], "SCV008144391")
            self.assertEqual(submission["submitter"], "Myriad Genetics, Inc.")
            self.assertEqual(submission["germline_classification"], "Pathogenic")
            self.assertEqual(submission["method"], "clinical testing")

    async def test_validation_all_tools(self):
        with patch.dict(os.environ, {"NCBI_EMAIL": "researcher@example.org"}):
            for func, args in [(api.clinvar_search, {"query": ""}),
                               (api.clinvar_search, {"query": "x", "limit": 101}),
                               (api.clinvar_variant, {"variation_id": "bad id"}),
                               (api.clinvar_variant, {"variation_id": "SCV000000001"}),
                               (api.clinvar_variants, {"variation_ids": []}),
                               (api.clinvar_variants, {"variation_ids": ["RCV1"]}),
                               (api.clinvar_variants, {"variation_ids": [str(i) for i in range(51)]}),
                               (api.clinvar_rcv, {"rcv_accession": "SCV000000001"}),
                               (api.clinvar_rcv, {"rcv_accession": "RCV12345"})]:
                with self.subTest(tool=func.__name__), self.assertRaises(ValueError):
                    await func(**args)

    async def test_missing_email(self):
        with patch.dict(os.environ, {}, clear=True):
            for func in [api.clinvar_search, api.clinvar_variant, api.clinvar_variants, api.clinvar_rcv]:
                with self.subTest(tool=func.__name__), self.assertRaises(ValueError):
                    await func(**({"variation_ids": ["1"]} if func is api.clinvar_variants
                                  else {"query": "x"} if func is api.clinvar_search
                                  else {"variation_id": "1"} if func is api.clinvar_variant
                                  else {"rcv_accession": "RCV000000001"}))

    async def test_source_urls_remove_api_key_for_json_and_xml(self):
        def handler(req):
            self.assertEqual(req.url.params["api_key"], "TEST_SECRET")
            return httpx.Response(200, text=RCV_XML) if "efetch" in req.url.path else httpx.Response(200, json=ESUMMARY)
        with patch.dict(os.environ, {"NCBI_API_KEY": "TEST_SECRET"}), self.mock_http(handler):
            for result in (await api.clinvar_variant("5042478"), await api.clinvar_rcv("RCV000000001")):
                self.assertNotIn("TEST_SECRET", result["source_url"])
                self.assertNotIn("email=", result["source_url"])

    async def test_api_error(self):
        with patch.dict(os.environ, {"NCBI_EMAIL": "researcher@example.org"}):
            with self.mock_http(lambda req: httpx.Response(404)):
                with self.assertRaises(httpx.HTTPStatusError):
                    await api.clinvar_variant("5042478")

