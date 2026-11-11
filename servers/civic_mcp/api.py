"""CIViC precision oncology knowledgebase: genes, variants and evidence items."""
from __future__ import annotations

from typing import Any

from common.api import choice, json_response, local_page
from common.http import bounded, identifier, text

BASE = "https://civicdb.org/api/graphql"
ENTITIES = {"FEATURE", "VARIANT", "EVIDENCE_ITEM", "ASSERTION", "VARIANT_GROUP",
            "MOLECULAR_PROFILE", "THERAPY", "DISEASE"}
GENE_FIELDS = ("id name fullName description entrezId featureAliases link "
               "stats { variantCount evidenceItemCount assertionCount molecularProfileCount }")
EVIDENCE_FIELDS = ("id name description evidenceType evidenceLevel evidenceDirection "
                   "significance variantOrigin status evidenceRating variantHgvs link "
                   "disease { id name } therapies { id name } phenotypes { id name } "
                   "source { id title citation }")
VARIANT_FIELDS = ("id name variantAliases variantTypes { id name } feature { id name } link")


def _id(value: str, name: str) -> int:
    return int(identifier(value, r"[0-9]+", f"CIViC {name} ID"))


def _cursor(cursor: str | None) -> str | None:
    return text(cursor, "cursor", 4000) if cursor is not None else None


async def _query(declarations: str, selection: str, variables: dict) -> dict:
    query = f"query({declarations}) {{ {selection} }}"
    result, source = await json_response(BASE, body={"query": query, "variables": variables})
    errors = result.get("errors", [])
    return {**source, "status": ("partial" if result.get("data") else "error") if errors else "ok",
            "data": result.get("data"), "errors": errors}


def _paged(result: dict, path: list[str], limit: int, offset: int) -> dict:
    data: Any = result.get("data")
    for key in path:
        data = (data or {}).get(key) if isinstance(data, dict) else None
    connection = data if isinstance(data, dict) else {}
    nodes = connection.get("nodes") or []
    info: dict[str, Any] = {"source_url": result["source_url"], "status": result["status"]}
    if result["errors"]:
        info["errors"] = result["errors"]
    page = local_page(nodes, limit, offset, **info)
    page.update({"totalCount": connection.get("totalCount", page["total"]),
                 "end_cursor": connection.get("pageInfo", {}).get("endCursor"),
                 "has_next_page": connection.get("pageInfo", {}).get("hasNextPage"),
                 "pagination": "local"})
    return page


async def civic_search(query: str, entity: str = "FEATURE", limit: int = 20,
                       offset: int = 0) -> dict:
    """Search CIViC genes/features, variants, evidence items, assertions, therapies or diseases.

    The upstream search is unpaginated; results are sliced locally.
    """
    choice(entity, ENTITIES, "entity")
    result = await _query("$query: String!, $types: [SearchableEntities!]",
                          "search(query: $query, types: $types) "
                          "{ id name resultType matchingText link }",
                          {"query": text(query), "types": [entity]})
    rows = (result.get("data") or {}).get("search") or []
    info: dict[str, Any] = {"source_url": result["source_url"], "status": result["status"]}
    if result["errors"]:
        info["errors"] = result["errors"]
    return local_page(rows, limit, offset, **info)


async def civic_gene(gene_id: str | None = None, entrez_symbol: str | None = None) -> dict:
    """Retrieve a CIViC gene/feature by CIViC ID or Entrez symbol, with usage statistics."""
    if (gene_id is None) == (entrez_symbol is None):
        raise ValueError("Provide exactly one of gene_id and entrez_symbol")
    if gene_id is not None:
        return await _query("$id: Int", f"gene(id: $id) {{ {GENE_FIELDS} }}",
                            {"id": _id(gene_id, "gene")})
    return await _query("$symbol: String", f"gene(entrezSymbol: $symbol) {{ {GENE_FIELDS} }}",
                        {"symbol": identifier(entrez_symbol or "", r"[A-Za-z0-9_.-]+",
                                              "Entrez symbol")})


async def civic_gene_variants(gene_id: str, limit: int = 20, offset: int = 0,
                              cursor: str | None = None) -> dict:
    """List curated variants of one gene, keeping the upstream cursor for deep paging."""
    variables = {"id": _id(gene_id, "gene"), "first": bounded(limit),
                 "after": _cursor(cursor)}
    result = await _query("$id: Int!, $first: Int, $after: String",
                          "gene(id: $id) { variants(first: $first, after: $after) "
                          f"{{ nodes {{ {VARIANT_FIELDS} }} "
                          "pageInfo { endCursor hasNextPage } totalCount } } }", variables)
    return _paged(result, ["gene", "variants"], limit, offset)


async def civic_variant(variant_id: str) -> dict:
    """Retrieve a CIViC variant, its aliases, variant types and parent gene/feature."""
    return await _query("$id: Int!", f"variant(id: $id) {{ {VARIANT_FIELDS} }}",
                        {"id": _id(variant_id, "variant")})


async def civic_evidence_item(evidence_id: str) -> dict:
    """Retrieve a CIViC evidence item with its clinical meaning, disease, therapies and source."""
    return await _query("$id: Int!", f"evidenceItem(id: $id) {{ {EVIDENCE_FIELDS} }}",
                        {"id": _id(evidence_id, "evidence item")})


async def civic_variant_evidence(variant_id: str, limit: int = 20, offset: int = 0,
                                 cursor: str | None = None) -> dict:
    """List evidence items supporting one variant, keeping the upstream cursor for deep paging."""
    variables = {"id": _id(variant_id, "variant"), "first": bounded(limit),
                 "after": _cursor(cursor)}
    result = await _query("$id: Int!, $first: Int, $after: String",
                          "evidenceItems(variantId: $id, first: $first, after: $after) "
                          f"{{ nodes {{ {EVIDENCE_FIELDS} }} "
                          "pageInfo { endCursor hasNextPage } totalCount } }", variables)
    return _paged(result, ["evidenceItems"], limit, offset)


TOOLS = (
    civic_search,
    civic_gene,
    civic_gene_variants,
    civic_variant,
    civic_evidence_item,
    civic_variant_evidence,
)


RESOURCES = ()
