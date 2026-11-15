"""Alliance of Genome Resources: genes, phenotypes, orthologs and search.

The Alliance (https://www.alliancegenome.org) aggregates gene-centric data from
the model-organism databases MODs (FlyBase, WormBase, MGI, SGD, ZFIN, RGD) plus
human (HGNC). The public REST API under /api requires no key; this integration
uses bounded JSON GET requests only, preserves upstream pagination for /search
and slices gene sub-resource lists locally. No downloads, no HTML scraping.

Endpoint shapes below were verified live against production (sample responses
from /gene/FB:FBgn0000606, /gene/WB:WBGene00003055, /gene/{id}/phenotypes,
/gene/{id}/orthologs and /search?q=p53&limit=2):

* Gene lookup requires the member-database prefix (/gene/FBgn0000606 alone
  returns 400; FB:FBgn0000606, WB:WBGene00003055, MGI:98297, RGD:3889 and
  HGNC:11998 resolve). Bare FlyBase/WormBase/ZFIN/SGD identifiers are
  normalized here by prepending the matching member prefix.
* Gene summaries nest under top-level "gene" with curated keys (geneSymbol,
  geneFullName, geneType, taxon, dataProvider, crossReferences, geneSynonyms);
  sub-resources return {"results": [...], "total": N, "returnedRecords": N}.
* Bare identifiers normalize with or without a "primary" marker: ZDB-GENE-
  990415-72 resolves as ZFIN:ZDB-GENE-990415-72 and S000006158 resolves as
  SGD:S000006158 (the bare SGD form has no distinguishing prefix beyond the
  leading S and six trailing digits).

Known upstream gap (verified live): GET /gene/{id}/diseases returns
"Resource not found" for every identifier, so disease hits are reached
through /search (see alliance_disease_search).

The /gene/{id}/alleles sub-resource has NOT been verified live (egress to
the Alliance API is WAF-challenged from this environment); alliance_alleles
tries it first and falls back to /allele/search when it returns 404. The
allele row mapping is therefore provisional and may need adjustment once a
live sample confirms the response shape.
"""
from __future__ import annotations

from typing import Annotated, Any
import re

import httpx
from pydantic import Field

from common.api import local_page, page
from common.http import bounded, request, safe_url, text

BASE = "https://www.alliancegenome.org/api"

# Bare MOD identifier -> member-database prefix.
_BARE_PREFIXES: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"FB(?:gn|pp|tr|al)[0-9]{7}", re.IGNORECASE), "FB"),
    (re.compile(r"WBGene[0-9]{8}"), "WB"),
    (re.compile(r"ZDB-GENE-[0-9]{6}-[0-9]+"), "ZFIN"),
    (re.compile(r"S[0-9]{6}"), "SGD"),
)
_CURIE = re.compile(r"[A-Z][A-Za-z0-9]*:[A-Za-z0-9_.-]+")


def _gene_id(value: str) -> str:
    value = text(value, "gene_id", 150)
    if ":" not in value:
        for pattern, prefix in _BARE_PREFIXES:
            if pattern.fullmatch(value):
                return f"{prefix}:{value}"
        raise ValueError("Invalid gene_id")
    prefix, _, local = value.partition(":")
    normalized = f"{prefix.upper()}:{local}"
    if not _CURIE.fullmatch(normalized):
        raise ValueError("Invalid gene_id")
    return normalized


async def _get(path: str, params: dict | None = None) -> tuple[Any, dict]:
    """Fetch one bounded JSON document, mapping upstream rejections explicitly."""
    try:
        response = await request("GET", f"{BASE}/{path}", params=params)
    except httpx.HTTPStatusError as exc:
        status = exc.response.status_code
        if status == 404:
            return None, {"source_url": safe_url(exc.request.url)}
        if status == 400:
            raise ValueError(f"Alliance API rejected the request for {path} "
                             "(unknown or malformed identifier)") from None
        raise
    return response.json(), {"source_url": safe_url(response.url)}


def _results(payload: Any) -> list:
    """Return the upstream results array of a list endpoint or search page."""
    if isinstance(payload, list):
        return payload
    if isinstance(payload, dict) and isinstance(payload.get("results"), list):
        return payload["results"]
    return []


def _status(payload: Any) -> str:
    return "not_found" if payload in (None, [], {}) else "ok"


def _display(value: Any) -> Any:
    """Extract display text from the curated {formatText, displayText} objects."""
    if isinstance(value, dict) and "displayText" in value:
        return value["displayText"]
    return value


def _gene_summary(gene: dict) -> dict:
    taxon = gene.get("taxon") or {}
    species = taxon.get("species") or {}
    provider = gene.get("dataProvider") or {}
    return {
        "curie": gene.get("curie"),
        "primary_external_id": gene.get("primaryExternalId"),
        "symbol": _display(gene.get("geneSymbol")),
        "name": _display(gene.get("geneFullName")),
        "systematic_name": _display(gene.get("geneSystematicName")),
        "gene_type": (gene.get("geneType") or {}).get("name"),
        "so_term_id": (gene.get("geneType") or {}).get("curie"),
        "taxon": {"curie": taxon.get("curie"), "name": taxon.get("name"),
                  "species": species.get("fullName")},
        "data_provider": {"abbreviation": provider.get("abbreviation"),
                          "full_name": provider.get("fullName")},
        "cross_references": [{"referenced_curie": item.get("referencedCurie"),
                              "display_name": item.get("displayName")}
                             for item in gene.get("crossReferences") or []
                             if isinstance(item, dict)],
        "synonyms": [_display(item) for item in gene.get("geneSynonyms") or []],
    }


def _phenotype_row(record: dict) -> dict:
    annotations = record.get("primaryAnnotations") or []
    return {"phenotype_statement": record.get("phenotypeStatement"),
            "relation": (record.get("relation") or {}).get("name"),
            "annotation_curies": [item.get("curie") for item in annotations
                                  if isinstance(item, dict)],
            "data_providers": sorted({(item.get("dataProvider") or {}).get("abbreviation")
                                      for item in annotations
                                      if isinstance(item, dict) and item.get("dataProvider")}),
            "evidence_curies": sorted({((item.get("evidenceItem") or {}).get("curie"))
                                       for item in annotations
                                       if isinstance(item, dict) and item.get("evidenceItem")}),
            "reference_curies": [item.get("referencedCurie")
                                 for item in record.get("references") or []],
            "pubmed_publication_count": len(record.get("pubmedPublications") or [])}


def _ortholog_row(record: dict) -> dict:
    generated = record.get("geneToGeneOrthologyGenerated") or {}

    def member(side: str) -> dict:
        gene = generated.get(side) or {}
        return {"curie": gene.get("curie"),
                "primary_external_id": gene.get("primaryExternalId"),
                "symbol": _display(gene.get("geneSymbol")),
                "species": ((gene.get("taxon") or {}).get("species") or {}).get("fullName")}

    return {"stringency": record.get("stringencyFilter"),
            "confidence": (generated.get("confidence") or {}).get("name"),
            "best_score": (generated.get("isBestScore") or {}).get("name"),
            "best_score_reverse": (generated.get("isBestScoreReverse") or {}).get("name"),
            "subject_gene": member("subjectGene"),
            "object_gene": member("objectGene"),
            "methods_matched": [(item or {}).get("name")
                                for item in generated.get("predictionMethodsMatched") or []],
            "methods_not_matched": [(item or {}).get("name")
                                    for item in generated.get("predictionMethodsNotMatched") or []],
            "source_member_databases": sorted({(item or {}).get("name")
                                               for item in generated.get("predictionMethodsMatched") or []
                                               if (item or {}).get("name") in
                                               {"HGNC", "MGI", "RGD", "ZFIN", "FB", "WB", "SGD"}})}


def _search_row(record: dict) -> dict:
    return {"id": record.get("id"), "curie": record.get("curie"),
            "category": record.get("category"), "symbol": record.get("symbol"),
            "name": record.get("name"), "species": record.get("species"),
            "so_term_name": record.get("soTermName"), "score": record.get("score")}


def _allele_row(record: dict) -> dict:
    """Map an allele record; provisional until a live sample confirms the shape."""
    symbol = record.get("symbol")
    if isinstance(symbol, dict):
        symbol = _display(symbol)
    name = record.get("name")
    if isinstance(name, dict):
        name = _display(name)
    return {"id": record.get("id"), "curie": record.get("curie"),
            "category": record.get("category"), "symbol": symbol, "name": name,
            "species": record.get("species")}


async def alliance_gene(gene_id: str) -> dict:
    """Retrieve an Alliance gene summary by MOD or AGRKB identifier.

    Accepts prefixed CURIEs (HGNC:11998, MGI:98297, RGD:3889, ZFIN:ZDB-GENE-...,
    SGD:S000006158, FB:FBgn0000606, WB:WBGene00003055, AGRKB:...) and bare
    FlyBase/WormBase/ZFIN/SGD IDs such as FBgn0000606 or WBGene00003055, which
    are normalized by prepending the member prefix. Returns symbol, full and
    systematic name, gene type with SO term, taxon/species, primary external
    ID, data provider, cross-references and synonyms, plus the full upstream
    gene object. Unknown identifiers return status "not_found".
    """
    value = _gene_id(gene_id)
    payload, source = await _get(f"gene/{value}")
    gene = payload.get("gene") if isinstance(payload, dict) else None
    if gene is None:
        return {**source, "gene_id": value, "status": _status(payload)}
    return {**source, "gene_id": value, "status": "ok",
            "data": _gene_summary(gene), "gene": gene}


async def alliance_gene_phenotypes(gene_id: str, limit: int = 20, offset: int = 0) -> dict:
    """List phenotype annotations for one gene, paginated locally.

    Each row reports the curated phenotype statement, its relation (usually
    has_phenotype), annotation curies, evidence, contributing member database
    and references. An empty list means the gene has no curated phenotypes
    (total 0), not an error.
    """
    value = _gene_id(gene_id)
    page(limit, offset)  # validate before the network request
    payload, source = await _get(f"gene/{value}/phenotypes")
    return {**source, "gene_id": value, "status": _status(payload),
            **local_page([_phenotype_row(row) for row in _results(payload)
                          if isinstance(row, dict)], limit, offset,
                         upstream_total=payload.get("total")
                         if isinstance(payload, dict) else None)}


async def alliance_orthologs(gene_id: str, limit: int = 20, offset: int = 0) -> dict:
    """List cross-species orthologs for one gene, paginated locally.

    Each row pairs the query gene with one ortholog from the Alliance DIOPT
    aggregation, keeping the confidence, best-score flags, the methods that
    matched and the source member databases behind them.
    """
    value = _gene_id(gene_id)
    page(limit, offset)  # validate before the network request
    payload, source = await _get(f"gene/{value}/orthologs")
    return {**source, "gene_id": value, "status": _status(payload),
            **local_page([_ortholog_row(row) for row in _results(payload)
                          if isinstance(row, dict)], limit, offset)}


async def alliance_alleles(gene_id: str, limit: int = 20, offset: int = 0) -> dict:
    """List alleles for one gene, paginated locally.

    Tries the gene sub-resource GET /gene/{id}/alleles first; if that returns
    404 upstream, falls back to /allele/search filtered by the gene's primary
    external ID. NOTE: neither endpoint shape has been verified live from
    this environment (Alliance egress is WAF-challenged here), so the allele
    row mapping below is provisional and the fallback query parameter may
    need adjustment once a live sample is captured. Limit/offset and the
    gene identifier are validated before any network request.
    """
    value = _gene_id(gene_id)
    page(limit, offset)  # validate before the network request
    payload, source = await _get(f"gene/{value}/alleles")
    if payload is None:
        payload, source = await _get("allele/search", {"primaryId": value})
    return {**source, "gene_id": value, "status": _status(payload),
            **local_page([_allele_row(row) for row in _results(payload)
                          if isinstance(row, dict)], limit, offset,
                         upstream_total=payload.get("total")
                         if isinstance(payload, dict) else None)}


async def alliance_search(query: str, category: str | None = None,
                          limit: Annotated[int, Field(ge=1, le=100)] = 20,
                          offset: Annotated[int, Field(ge=0, le=1_000_000)] = 0) -> dict:
    """Free-text search across Alliance entities (genes, variants, diseases, ...).

    The upstream /search endpoint ignores a category filter parameter and
    returns category aggregations alongside the result page, so this tool
    passes only q, limit and offset upstream (pagination preserved verbatim)
    and optionally filters the returned page locally by entity category such
    as "gene_search_result" or "disease_search_result"; category_totals shows
    the upstream counts per category. Resolve genes with alliance_gene using
    the returned curie.
    """
    limit, offset = bounded(limit), bounded(offset, 1_000_000, "offset", 0)
    if category is not None and not isinstance(category, str):
        raise ValueError("category must be a string such as gene_search_result")
    payload, source = await _get("search", {"q": text(query, "query", 300),
                                            "limit": limit, "offset": offset})
    aggregations = payload.get("aggregations") if isinstance(payload, dict) else None
    category_totals = {item.get("key"): item.get("total")
                       for group in aggregations or []
                       if isinstance(group, dict) and group.get("key") == "category"
                       for item in group.get("values") or [] if isinstance(item, dict)}
    rows = [_search_row(row) for row in _results(payload) if isinstance(row, dict)]
    if category is not None:
        if not isinstance(category, str):
            raise ValueError("category must be a string such as gene_search_result")
        rows = [row for row in rows if row.get("category") == category]
    return {**source, "query": query, "status": _status(payload),
            "total": payload.get("total") if isinstance(payload, dict) else None,
            "category_totals": category_totals,
            **({"category": category} if category else {}),
            **(local_page(rows, limit, offset, pagination="local")
               if category else
               {"limit": limit, "offset": offset,
                "results": rows, "pagination": "upstream"})}


async def alliance_disease_search(query: str, limit: int = 20, offset: int = 0) -> dict:
    """Search Alliance disease entities by free text.

    Thin wrapper over the same upstream /search endpoint used by
    alliance_search: no category parameter is sent upstream (the endpoint
    ignores it, verified live) and results are filtered locally to the
    "disease_search_result" category, so the returned page reflects the
    upstream page's slice of disease hits. category_totals shows the
    upstream counts per category; the upstream "total" covers all
    categories. Argument validation happens before any network request.
    """
    text(query, "query", 300)
    page(limit, offset)  # validate before the network request
    return await alliance_search(query, category="disease_search_result",
                                 limit=limit, offset=offset)


TOOLS = (
    alliance_gene,
    alliance_gene_phenotypes,
    alliance_orthologs,
    alliance_search,
    alliance_disease_search,
    alliance_alleles,
)


def _member_databases() -> dict:
    """List the Alliance member databases and identifier prefixes accepted here."""
    return {"member_databases": sorted({"HGNC", "MGI", "RGD", "ZFIN", "FB", "WB", "SGD"}),
            "bare_id_prefixes": {"FBgn/FBpp/FBtr/FBal": "FB", "WBGene": "WB",
                                 "ZDB-GENE-": "ZFIN", "S000000-style": "SGD"},
            "gene_id_format": "prefix:local CURIE (e.g. FB:FBgn0000606, HGNC:11998); bare MOD ids are auto-prefixed"}


RESOURCES = (
    ("alliance://member_databases", _member_databases),
)
