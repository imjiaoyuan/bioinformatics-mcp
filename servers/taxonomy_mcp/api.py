"""NCBI Taxonomy and GBIF backbone taxon lookup, search and hierarchy.

NCBI Taxonomy is queried through E-utilities (esearch/esummary/efetch,
db "taxonomy"); a contact e-mail is required via NCBI_EMAIL and an API
key is honoured via NCBI_API_KEY. GBIF species match/detail/search uses
the public backbone API. No files are downloaded; responses are bounded
and every result carries the source URL.
"""
from __future__ import annotations

import os
import xml.etree.ElementTree as ET
from typing import Annotated, Any
from urllib.parse import quote

from pydantic import Field

from common.api import local_page, page
from common.http import bounded, identifier, request, safe_url, text

BASE = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"
GBIF = "https://api.gbif.org/v1/species"
GBIF_INTERVAL = 0.1
GBIF_PAGE_SIZE = 100
GBIF_MAX_ROWS = 1_000


def _config() -> dict[str, str]:
    email = os.environ.get("NCBI_EMAIL")
    if not email:
        raise ValueError("NCBI_EMAIL must be set (for example researcher@example.org)")
    config = {"email": email, "tool": "taxonomy-mcp"}
    if api_key := os.environ.get("NCBI_API_KEY"):
        config["api_key"] = api_key
    return config


async def _get(endpoint: str, params: dict[str, str], *, retmode: str = "json") -> dict:
    """GET one E-utility endpoint with a polite interval and a traceable URL."""
    interval = 0.11 if "api_key" in (config := _config()) else 0.35
    response = await request("GET", f"{BASE}/{endpoint}.fcgi",
                             params={**params, **config, "retmode": retmode},
                             interval=interval)
    if retmode == "xml":
        return {**_parse_taxon(response.text), "source_url": safe_url(response.url)}
    data = response.json()
    if isinstance(data, dict) and "error" in data:
        raise RuntimeError(f"NCBI error: {data['error']}")
    return {**data, "source_url": safe_url(response.url)}


async def _search_uids(term: str, limit: int, offset: int) -> tuple[int, list[str]]:
    data = await _get("esearch", {"db": "taxonomy", "term": term,
                                  "retmax": str(limit), "retstart": str(offset)})
    result = data.get("esearchresult", {})
    return int(result.get("count", "0")), result.get("idlist", [])


def _taxid(value: str) -> str:
    return identifier(value.strip(), r"[0-9]+", "NCBI taxonomy ID")


def _first(element: ET.Element, tag: str) -> str | None:
    if (found := element.find(tag)) is not None and found.text:
        return found.text.strip()
    return None


def _parse_taxon(xml_text: str) -> dict[str, Any]:
    """Parse one efetch taxonomy XML record into names, rank and lineage."""
    root = ET.fromstring(xml_text)
    taxon = root.find("Taxon")
    if taxon is None:
        raise RuntimeError("NCBI returned no taxonomy record")
    lineage = [node for node in taxon.findall("LineageEx/Taxon")
               if (node.findtext("TaxId") or "").strip() != (taxon.findtext("TaxId") or "").strip()]
    return {"taxid": _first(taxon, "TaxId"),
            "scientific_name": _first(taxon, "ScientificName"),
            "common_name": _first(taxon, "OtherNames/GenbankCommonName"),
            "rank": _first(taxon, "Rank"),
            "division": _first(taxon, "Division"),
            "lineage": _first(taxon, "Lineage"),
            "lineage_summary": [{"taxid": node.findtext("TaxId").strip(),
                                 "name": node.findtext("ScientificName"),
                                 "rank": node.findtext("Rank")} for node in lineage],
            "create_date": _first(taxon, "CreateDate"),
            "update_date": _first(taxon, "UpdateDate")}


def _summary(summary: dict[str, Any]) -> dict[str, Any]:
    """Extract one taxonomy docsum: taxid, names, rank and division."""
    return {"taxid": summary.get("taxid") or summary.get("uid"),
            "scientific_name": summary.get("scientificname"),
            "common_name": summary.get("commonname"),
            "rank": summary.get("rank"),
            "division": summary.get("division"),
            "status": summary.get("status"),
            "modified": summary.get("modificationdate")}


async def taxon_lookup(taxon_id: str) -> dict:
    """Retrieve one NCBI Taxonomy node by numeric taxid with rank and lineage.

    Uses efetch (db=taxonomy, XML) so the full parent lineage summary and
    division are returned alongside the scientific and common names.
    """
    value = _taxid(taxon_id)
    data = await _get("efetch", {"db": "taxonomy", "id": value}, retmode="xml")
    if not data.get("taxid"):
        raise ValueError(f"No NCBI taxonomy node found for taxid {value}")
    return data


async def taxon_search(query: str, limit: int = 20, offset: int = 0) -> dict:
    """Search NCBI Taxonomy with Entrez syntax and return docsum rows.

    Use plain names (``Homo sapiens``) or field-qualified terms such as
    ``Homo[genus]``; paging maps to retstart/retmax upstream.
    """
    term = text(query, "query", 500)
    paging = page(limit, offset)
    count, uids = await _search_uids(term, paging["limit"], paging["offset"])
    rows: list[dict[str, Any]] = []
    source_url = f"{BASE}/esearch.fcgi?db=taxonomy&term={quote(term)}"
    if uids:
        data = await _get("esummary", {"db": "taxonomy", "id": ",".join(uids)})
        result = data.get("result", {})
        rows = [_summary(result[uid]) for uid in uids if uid in result]
        source_url = data["source_url"]
    return {**paging, "query": term, "count": count, "results": rows,
            "source_url": source_url}


async def taxon_children(taxon_id: str, limit: int = 20, offset: int = 0) -> dict:
    """List the direct children of one NCBI taxonomy node.

    Upstream quirk: the documented ``{taxid}[TaxNode:children]`` term is
    silently rewritten to ``{taxid}[All Names]`` by esearch on db=taxonomy
    and matches nothing useful. The working approach (verified live) is
    the organism-expansion term ``txid{taxid}[Organism:exp]``, which
    expands a node to itself plus its immediate children; the parent
    taxid is then removed locally and the remaining UIDs are summarised.
    """
    value = _taxid(taxon_id)
    paging = page(limit, offset)
    count, uids = await _search_uids(f"txid{value}[Organism:exp]",
                                     min(paging["offset"] + paging["limit"] + 1, 100), 0)
    children = [uid for uid in uids if uid != value]
    count = max(0, count - 1)  # the expansion always includes the node itself
    rows: list[dict[str, Any]] = []
    source_url = f"{BASE}/esearch.fcgi?db=taxonomy&term=txid{value}%5BOrganism%3Aexp%5D"
    if children:
        data = await _get("esummary", {"db": "taxonomy", "id": ",".join(children)})
        result = data.get("result", {})
        source_url = data["source_url"]
        rows = [_summary(result[uid]) for uid in children if uid in result]
    return local_page(rows, paging["limit"], paging["offset"], taxid=value, count=count,
                      source_url=source_url)


async def taxon_gbif_match(name: str, strict: bool = False) -> dict:
    """Match a scientific or vernacular name against the GBIF backbone.

    Returns usageKey, scientificName, rank, matchType and confidence;
    unmatched names come back with matchType NONE and a null usageKey
    (raise nothing, so callers can inspect the near-miss alternatives).
    """
    value = text(name, "name", 200)
    response = await request("GET", f"{GBIF}/match", params={"name": value, "strict": str(strict).lower()},
                             interval=GBIF_INTERVAL)
    data = response.json()
    if match_type := data.get("matchType"):
        if match_type == "NONE":
            return {"match_type": "NONE", "name": value, "usage_key": None,
                    "scientific_name": None, "rank": None, "confidence": 0,
                    "synonyms": [], "note": "No GBIF backbone match",
                    "source_url": safe_url(response.url)}
        return {"match_type": match_type, "name": value,
                "usage_key": data.get("usageKey"),
                "scientific_name": data.get("scientificName"),
                "canonical_name": data.get("canonicalName"),
                "rank": data.get("rank"), "status": data.get("status"),
                "confidence": data.get("confidence"),
                "kingdom": data.get("kingdom"), "phylum": data.get("phylum"),
                "class": data.get("class"), "order": data.get("order"),
                "family": data.get("family"), "genus": data.get("genus"),
                "synonyms": [], "source_url": safe_url(response.url)}
    raise RuntimeError(f"GBIF returned no matchType for name {value!r}")


async def _gbif_rows(url: str, params: dict[str, Any]) -> tuple[list[dict[str, Any]], str, int]:
    """Collect up to GBIF_MAX_ROWS GBIF rows across offset pages."""
    rows: list[dict[str, Any]] = []
    offset = 0
    source_url = ""
    count = 0
    while offset < GBIF_MAX_ROWS:
        response = await request("GET", url, params={**params, "limit": GBIF_PAGE_SIZE, "offset": offset},
                                 interval=GBIF_INTERVAL)
        source_url = safe_url(response.url)
        data = response.json()
        batch = data.get("results", [])
        rows.extend(batch)
        count = int(data.get("count", 0) or 0)
        offset += GBIF_PAGE_SIZE
        if not batch or data.get("endOfRecords", True):
            break
    return rows, source_url, count


def _constituents(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [{"key": row.get("key"), "scientific_name": row.get("scientificName"),
             "canonical_name": row.get("canonicalName"), "rank": row.get("rank"),
             "taxonomic_status": row.get("taxonomicStatus"),
             "vernacular_names": sorted({item.get("vernacularName") for item in row.get("vernacularNames", [])
                                         if item.get("vernacularName")})}
            for row in rows]


async def taxon_gbif_species(usage_key: Annotated[int, Field(ge=1, le=99_999_999_999)],
                             limit: int = 20, offset: int = 0) -> dict:
    """Retrieve GBIF backbone species detail for a usage key with constituents.

    Returns the accepted/verbatim record (classification, basionym,
    vernacular names) and, for higher ranks, the immediate constituent
    taxa collected across paginated /children calls and sliced locally.
    """
    key = bounded(usage_key, 99_999_999_999, "usage_key", 1)
    response = await request("GET", f"{GBIF}/{key}", interval=GBIF_INTERVAL)
    detail = response.json()
    if "key" not in detail:
        raise ValueError(f"No GBIF backbone usage found for key {key}")
    source_url = safe_url(response.url)
    rows: list[dict[str, Any]] = []
    if detail.get("numDescendants"):
        child_rows, children_url, _ = await _gbif_rows(f"{GBIF}/{key}/children", {})
        rows = _constituents(child_rows)
        source_url = children_url
    return {"usage_key": key, "scientific_name": detail.get("scientificName"),
            "canonical_name": detail.get("canonicalName"),
            "rank": detail.get("rank"), "taxonomic_status": detail.get("taxonomicStatus"),
            "accepted": detail.get("accepted"), "accepted_key": detail.get("acceptedKey"),
            "parent": detail.get("parent"), "parent_key": detail.get("parentKey"),
            "kingdom": detail.get("kingdom"), "phylum": detail.get("phylum"),
            "class": detail.get("class"), "order": detail.get("order"),
            "family": detail.get("family"), "genus": detail.get("genus"),
            "num_descendants": detail.get("numDescendants"),
            "vernacular_names": sorted({item.get("vernacularName")
                                        for item in detail.get("vernacularNames", [])
                                        if item.get("vernacularName")}),
            "synonyms": [], "issues": detail.get("issues", []),
            "constituents": local_page(rows, limit, offset, pagination="local"),
            "source_url": source_url}


TOOLS = (
    taxon_lookup,
    taxon_search,
    taxon_children,
    taxon_gbif_match,
    taxon_gbif_species,
)


def _databases() -> dict:
    """List the taxonomy backends and endpoints served by this provider."""
    return {"ncbi_taxonomy": {"db": "taxonomy",
                              "endpoints": ["efetch (XML record with lineage)",
                                            "esearch/esummary (search and docsums)"],
                              "requires": "NCBI_EMAIL (NCBI_API_KEY optional)"},
            "gbif_backbone": {"base": GBIF,
                              "endpoints": ["/match", "/{usageKey}", "/{usageKey}/children"],
                              "max_rows": GBIF_MAX_ROWS}}


RESOURCES = (
    ("taxonomy://databases", _databases),
)
