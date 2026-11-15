"""QuickGO ontology terms, GO annotations and GO slim mapping."""
from __future__ import annotations

import json
from typing import Annotated, Literal

from pydantic import Field

from common.api import choice, json_response, local_page
from common.http import bounded, identifier, identifiers, text

BASE = "https://www.ebi.ac.uk/QuickGO/services"
GO_PATTERN = r"GO:[0-9]{7}"
RELATIONS = {"isa", "part_of"}
Aspects = Literal["biological_process", "cellular_component", "molecular_function"]


def _go_ids(values: list[str], name: str = "go_ids") -> list[str]:
    ids = identifiers(values, 50)
    return [identifier(value.upper(), GO_PATTERN, name) for value in ids]


async def _get(path: str, params: dict | None = None) -> dict:
    data, source = await json_response(f"{BASE}/{path}", params)
    return {**source, **data}


async def quickgo_go_term(go_ids: list[str]) -> dict:
    """Retrieve GO terms by identifier: names, definitions, aspect and hierarchy."""
    return await _get(f"ontology/go/terms/{','.join(_go_ids(go_ids))}")


async def quickgo_go_search(query: str, limit: Annotated[int, Field(ge=1, le=100)] = 20) -> dict:
    """Search GO terms by name or definition text."""
    return await _get("ontology/go/search", {"query": text(query), "limit": bounded(limit)})


async def quickgo_annotations(gene_product_id: str, go_id: str | None = None,
                              aspect: Aspects | None = None,
                              limit: Annotated[int, Field(ge=1, le=100)] = 20,
                              offset: Annotated[int, Field(ge=0, le=99_000)] = 0) -> dict:
    """Search GO annotations for one gene product; optionally filter by term or aspect.

    Offset selects the upstream page by slices of limit; results keep upstream pageInfo.
    """
    params = {"geneProductId": identifier(gene_product_id, r"[A-Za-z0-9_.:-]+", "gene_product_id"),
              "limit": bounded(limit)}
    if go_id is not None:
        params["goId"] = _go_ids([go_id], "go_id")[0]
    if aspect is not None:
        params["aspect"] = choice(aspect, {"biological_process", "cellular_component", "molecular_function"}, "aspect")
    bounded(offset, 99_000, "offset", 0)
    if offset % limit:
        raise ValueError("offset must be a multiple of limit")
    return await _get("annotation/search", {**params, "page": offset // limit + 1})


async def quickgo_slim(go_ids: list[str], slim_ids: list[str],
                       relation: str = "isa,part_of") -> dict:
    """Map GO terms to their nearest GO slim ancestor via ancestor traversal.

    Each term is assigned its closest ancestor (or itself) present in slim_ids;
    terms without a slim ancestor report a null slim_id. Mapping is local.
    """
    slims = _go_ids(slim_ids, "slim_ids")
    slim_set = set(slims)
    relations = [choice(part.strip(), RELATIONS, "relation") for part in relation.split(",") if part.strip()]
    data, source = await json_response(
        f"{BASE}/ontology/go/terms/{','.join(_go_ids(go_ids))}/ancestors", {"relation": ",".join(relations)})
    rows = [{"term": term["id"], "name": term.get("name"), "aspect": term.get("aspect"),
             "slim_id": nearest, "direct": nearest == term["id"]}
            for term in data.get("results", [])
            for nearest in [next((candidate for candidate in [term["id"], *(term.get("ancestors") or [])]
                                  if candidate in slim_set), None)]]
    return {**source, "relation": relations, "slim_ids": slims, **local_page(rows, 20, 0)}


TOOLS = (
    quickgo_go_term,
    quickgo_go_search,
    quickgo_annotations,
    quickgo_slim,
)


def controlled_values() -> str:
    """List GO aspects, slim relations and identifier constraints."""
    return json.dumps({
        "aspects": ["biological_process", "cellular_component", "molecular_function"],
        "slim_relations": sorted(RELATIONS),
        "go_id_pattern": GO_PATTERN,
        "annotations": {"offset": "multiple of limit, 0-99000", "max_go_ids_per_call": 50},
    })


RESOURCES = (
    ("quickgo://controlled-values", controlled_values),
)
