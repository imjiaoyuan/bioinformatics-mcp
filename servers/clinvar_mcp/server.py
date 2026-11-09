"""NCBI ClinVar variant clinical significance via Entrez esearch/esummary/efetch.

Overlaps with the ncbi (general Entrez) server: use this server for
ClinVar-specific variant summaries and RCV clinical-significance records
parsed from E-utilities; use the ncbi server for other Entrez databases.
"""
from __future__ import annotations

import os
import xml.etree.ElementTree as ET
from typing import Any
from urllib.parse import quote

from common.api import local_page, page
from common.http import identifier, identifiers, request, text
from mcp.server.fastmcp import FastMCP

mcp = FastMCP("clinvar")
BASE = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"


def _config() -> dict[str, str]:
    email = os.environ.get("NCBI_EMAIL")
    if not email:
        raise ValueError("NCBI_EMAIL must be set (for example researcher@example.org)")
    config = {"email": email, "tool": "clinvar-mcp"}
    if api_key := os.environ.get("NCBI_API_KEY"):
        config["api_key"] = api_key
    return config


async def _get(endpoint: str, params: dict[str, str], *, retmode: str = "json") -> dict:
    """GET one E-utility endpoint with a polite interval and a traceable URL."""
    # Stay below the unauthenticated NCBI limit; API-key users can go faster.
    interval = 0.11 if "api_key" in (config := _config()) else 0.35
    response = await request("GET", f"{BASE}/{endpoint}.fcgi",
                             params={**params, **config, "retmode": retmode},
                             interval=interval)
    if retmode == "xml":
        return {**_parse_clinvarset(response.text), "source_url": str(response.url)}
    data = response.json()
    if isinstance(data, dict) and "error" in data:
        raise RuntimeError(f"NCBI error: {data['error']}")
    return {**data, "source_url": str(response.url)}


async def _search_ids(term: str, limit: int, offset: int) -> tuple[int, list[str]]:
    data = await _get("esearch", {"db": "clinvar", "term": term, **page(limit, offset)})
    result = data.get("esearchresult", {})
    return int(result.get("count", "0")), result.get("idlist", [])


def _summary(summary: dict[str, Any]) -> dict[str, Any]:
    """Extract one ClinVar docsum: accession, genes, locations, classifications."""
    germline = summary.get("germline_classification") or {}
    return {"uid": summary.get("uid"),
            "accession": summary.get("accession"),
            "title": summary.get("title"),
            "variant_type": summary.get("obj_type"),
            "genes": [gene.get("symbol") for gene in summary.get("genes", [])],
            "molecular_consequences": summary.get("molecular_consequence_list", []),
            "protein_change": summary.get("protein_change"),
            "germline_classification": {
                "description": germline.get("description"),
                "review_status": germline.get("review_status"),
                "last_evaluated": germline.get("last_evaluated"),
                "traits": [trait.get("trait_name") for trait in germline.get("trait_set", [])]},
            "locations": [{"assembly": loc.get("assembly_name"), "chromosome": loc.get("chr"),
                           "start": loc.get("start"), "stop": loc.get("stop")}
                          for measure in summary.get("variation_set", [])
                          for loc in measure.get("variation_loc", [])],
            "spdi": next((measure.get("canonical_spdi")
                          for measure in summary.get("variation_set", [])
                          if measure.get("canonical_spdi")), None),
            "submissions": {"scv": summary.get("supporting_submissions", {}).get("scv", []),
                            "rcv": summary.get("supporting_submissions", {}).get("rcv", [])}}


def _first(element: ET.Element, path: str) -> str | None:
    if (found := element.find(path)) is not None and found.text:
        return found.text.strip()
    return None


def _attrib(element: ET.Element, path: str, attribute: str) -> str | None:
    found = element.find(path)
    return found.get(attribute) if found is not None else None


def _preferred(element: ET.Element, tag: str) -> str | None:
    for name in element.iter(tag):
        for value in name.iter("ElementValue"):
            if value.get("Type") == "Preferred" and value.text:
                return value.text.strip()
    return None


def _parse_clinvarset(xml_text: str) -> dict[str, Any]:
    """Parse one efetch clinvarset XML record into classification and submissions."""
    root = ET.fromstring(xml_text)
    clinvar_set = root.find("ClinVarSet")
    if clinvar_set is None:
        raise RuntimeError("ClinVar returned no ClinVarSet record")
    reference = clinvar_set.find("ReferenceClinVarAssertion")
    if reference is None:
        raise RuntimeError("ClinVar returned no ReferenceClinVarAssertion")
    accession = _attrib(reference, "ClinVarAccession", "Acc")
    classification = reference.find("Classifications/GermlineClassification")
    if classification is None:
        classification = reference.find("Classifications")
    trait_set = reference.find("TraitSet")
    measure_set = reference.find("MeasureSet")
    submissions: list[dict[str, Any]] = []
    for assertion in clinvar_set.findall("ClinVarAssertion"):
        classification_node = assertion.find("Classification")
        submissions.append({"scv_accession": _attrib(assertion, "ClinVarAccession", "Acc"),
                            "submitter": _attrib(assertion, "ClinVarSubmissionID", "submitter"),
                            "germline_classification": (_first(classification_node, "GermlineClassification")
                                                        if classification_node is not None else None),
                            "review_status": _first(classification_node, "ReviewStatus"),
                            "method": _first(assertion, "ObservedIn/Method/MethodType"),
                            "comment": _first(classification_node, "Comment")})
    return {"rcv_accession": accession,
            "title": _first(clinvar_set, "Title"),
            "record_status": _first(reference, "RecordStatus"),
            "germline_classification": _first(classification, "Description"),
            "review_status": _first(classification, "ReviewStatus"),
            "last_evaluated": _attrib(classification, "Description", "DateLastEvaluated")
            if classification is not None else None,
            "trait": {"name": _preferred(trait_set, "Name") if trait_set is not None else None,
                      "type": trait_set.get("Type") if trait_set is not None else None,
                      "xrefs": [{"db": xref.get("DB"), "id": xref.get("ID")}
                                for xref in (trait_set.iter("XRef") if trait_set is not None else [])]},
            "variant": {"vcv_accession": measure_set.get("Acc") if measure_set is not None else None,
                        "name": _preferred(measure_set, "Name") if measure_set is not None else None,
                        "hgvs": sorted({attribute.text.strip() for attribute
                                        in reference.iter("Attribute")
                                        if (attribute.get("Type") or "").startswith("HGVS") and attribute.text}),
                        "gene": {"symbol": _preferred(measure_set, "Symbol") if measure_set is not None else None,
                                 "name": _preferred(measure_set, "Name") if measure_set is not None else None}},
            "submissions": submissions}


@mcp.tool()
async def clinvar_search(query: str, limit: int = 20, offset: int = 0) -> dict:
    """Search ClinVar variants with Entrez syntax; return matching variation UIDs and counts.

    Use field-qualified terms such as ``BRCA2[gene]`` and
    ``Pathogenic[clinical significance]``; combine terms with AND/OR.
    """
    count, uids = await _search_ids(text(query, "query"), limit, offset)
    return {**page(limit, offset), "query": query, "count": count, "uids": uids,
            "source_url": f"{BASE}/esearch.fcgi?db=clinvar&term={quote(query)}"}


@mcp.tool()
async def clinvar_variant(variation_id: str) -> dict:
    """Retrieve one ClinVar variant summary by numeric variation ID or VCV accession.

    Returns the preferred title, genes, germline classification, genomic
    locations, canonical SPDI and supporting SCV/RCV submission accessions.
    """
    value = identifier(variation_id.strip().upper(), r"(?:VCV)?[0-9]+", "ClinVar variation ID")
    if value.startswith("VCV"):
        count, uids = await _search_ids(value, 1, 0)
        if not uids:
            raise ValueError(f"No ClinVar record found for accession {value}")
        value = uids[0]
    data = await _get("esummary", {"db": "clinvar", "id": value})
    summary = data.get("result", {}).get(value)
    if not summary:
        raise RuntimeError(f"ClinVar returned no docsum for variation ID {value}")
    return {**_summary(summary), "source_url": data["source_url"]}


@mcp.tool()
async def clinvar_variants(variation_ids: list[str], limit: int = 20, offset: int = 0) -> dict:
    """Retrieve summaries for 1-50 ClinVar variation IDs in one esummary call.

    Results are sliced locally with explicit pagination metadata.
    """
    ids = identifiers(variation_ids, 50)
    for value in ids:
        identifier(value, r"[0-9]+", "ClinVar variation ID")
    data = await _get("esummary", {"db": "clinvar", "id": ",".join(ids)})
    result = data.get("result", {})
    rows = [_summary(summary) for uid in ids if (summary := result.get(uid))]
    return {**local_page(rows, limit, offset), "source_url": data["source_url"]}


@mcp.tool()
async def clinvar_rcv(rcv_accession: str) -> dict:
    """Retrieve the full clinical-significance record for one RCV accession.

    Returns the reference classification (description, review status), trait,
    variant HGVS expressions, gene and per-submitter SCV assertions parsed
    from the efetch clinvarset XML.
    """
    value = identifier(rcv_accession.strip().upper(), r"RCV[0-9]{9}", "RCV accession")
    return await _get("efetch", {"db": "clinvar", "id": value, "rettype": "clinvarset"}, retmode="xml")


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
