"""BiGG genome-scale metabolic models, reactions and metabolites."""
from __future__ import annotations

import json
from typing import Annotated, Literal

from pydantic import Field

from common.api import choice, json_response, local_page, page
from common.http import bounded, identifier, text

BASE = "https://bigg.ucsd.edu/api/v2"
_SEARCH_TYPES = {"models", "reactions", "metabolites", "genes"}
SearchType = Literal["models", "reactions", "metabolites", "genes"]
Limit = Annotated[int, Field(ge=1, le=100)]
Offset = Annotated[int, Field(ge=0, le=1_000_000)]


def _id(value: str, name: str = "identifier") -> str:
    return identifier(value, r"[A-Za-z0-9_][A-Za-z0-9_.+\[\]()!-]*", name)


async def _get(path: str, params: dict | None = None) -> dict:
    data, source = await json_response(f"{BASE}{path}", params)
    return {**source, **data}


def _slice(data: dict, limit: int, offset: int) -> dict:
    """Page a byte-bounded upstream list endpoint that has no pagination parameters."""
    return local_page(data["results"], bounded(limit), bounded(offset, 1_000_000, "offset", 0),
                      source_url=data["source_url"])


async def bigg_models(limit: Limit = 50, offset: Offset = 0) -> dict:
    """List available genome-scale models with organism and component counts.

    Results are paged locally; the upstream list endpoint has no pagination.
    """
    return _slice(await _get("/models"), limit, offset)


async def bigg_model(model_bigg_id: str) -> dict:
    """Retrieve model metadata including version, organism and component counts."""
    return await _get(f"/models/{_id(model_bigg_id, 'model_bigg_id')}")


async def bigg_model_reactions(model_bigg_id: str, limit: Limit = 50, offset: Offset = 0) -> dict:
    """List reactions in one model with names, stoichiometry summaries and bounds.

    Results are paged locally; the upstream list endpoint has no pagination.
    """
    _id(model_bigg_id, "model_bigg_id")
    return _slice(await _get(f"/models/{model_bigg_id}/reactions"), limit, offset)


async def bigg_model_metabolites(model_bigg_id: str, limit: Limit = 50, offset: Offset = 0) -> dict:
    """List metabolites in one model with names, compartments and model links.

    Results are paged locally; the upstream list endpoint has no pagination.
    """
    _id(model_bigg_id, "model_bigg_id")
    return _slice(await _get(f"/models/{model_bigg_id}/metabolites"), limit, offset)


async def bigg_reaction(model_bigg_id: str, reaction_bigg_id: str) -> dict:
    """Retrieve one model reaction's stoichiometry, bounds, gene rule and database links."""
    _id(model_bigg_id, "model_bigg_id")
    return await _get(f"/models/{model_bigg_id}/reactions/{_id(reaction_bigg_id, 'reaction_bigg_id')}")


async def bigg_metabolite(model_bigg_id: str, metabolite_bigg_id: str) -> dict:
    """Retrieve one model metabolite's compartment, formula, charge and reactions.

    Results identify the reactions that consume or produce the metabolite in the model.
    """
    _id(model_bigg_id, "model_bigg_id")
    return await _get(f"/models/{model_bigg_id}/metabolites/{_id(metabolite_bigg_id, 'metabolite_bigg_id')}")


async def bigg_search(query: str, search_type: SearchType = "reactions",
                      limit: Limit = 50, offset: Offset = 0) -> dict:
    """Search models, reactions, metabolites or genes by identifier substring.

    Valid search_type values are models, reactions, metabolites and genes.
    Results are paged locally; the upstream search endpoint has no pagination.
    """
    choice(search_type, _SEARCH_TYPES, "search_type")
    return _slice(await _get("/search", {**page(limit, offset),
                                         "query": text(query, "query", 100),
                                         "search_type": search_type}), limit, offset)


TOOLS = (
    bigg_models,
    bigg_model,
    bigg_model_reactions,
    bigg_model_metabolites,
    bigg_reaction,
    bigg_metabolite,
    bigg_search,
)


def search_types() -> str:
    """List the BiGG search types and paging constraints."""
    return json.dumps({"search_types": sorted(_SEARCH_TYPES),
                       "paging": {"limit": "1-100", "offset": "0-1000000", "mode": "local"},
                       "identifier_pattern": "[A-Za-z0-9_][A-Za-z0-9_.+[]()!-]*"})


RESOURCES = (
    ("bigg://search-types", search_types),
)
