"""IntAct molecular interactions, interactors and publication references."""
from __future__ import annotations

import json
from typing import Annotated

from pydantic import Field

from common.api import json_response, page
from common.http import identifier, text

BASE = "https://www.ebi.ac.uk/intact/ws"


async def _get(path: str, params: dict | None = None) -> dict:
    data, source = await json_response(f"{BASE}/{path}", params)
    return {**source, **data}


async def intact_interaction_search(query: str, limit: Annotated[int, Field(ge=1, le=100)] = 20,
                                    offset: Annotated[int, Field(ge=0, le=1_000_000)] = 0) -> dict:
    """Search molecular interactions by interactor identifier, gene name or interaction AC.

    Preserve upstream pagination metadata; the raw query is forwarded to IntAct search.
    """
    return await _get(f"interaction/findInteractions/{text(query, 'query', 300)}",
                      {"first": page(limit, offset)["offset"], "number": page(limit, offset)["limit"]})


async def intact_interactor_search(query: str, limit: Annotated[int, Field(ge=1, le=100)] = 20,
                                   offset: Annotated[int, Field(ge=0, le=1_000_000)] = 0) -> dict:
    """Search interactors (proteins, genes, small molecules) by identifier, name or alias."""
    return await _get(f"interactor/findInteractor/{text(query, 'query', 300)}",
                      {"first": page(limit, offset)["offset"], "number": page(limit, offset)["limit"]})


async def intact_interaction_details(interaction_ac: str) -> dict:
    """Retrieve one interaction with MI-type identifiers, detection method, intact-miscore and participants."""
    ac = identifier(interaction_ac.upper(), r"EBI-[0-9]+", "IntAct interaction AC")
    data = await _get(f"interaction/findInteractions/{ac}", {"first": 0, "number": 100})
    matches = [row for row in data.get("content", []) if row.get("ac") == ac]
    if not matches:
        raise ValueError(f"No IntAct interaction found for {ac}")
    return {**data, "interaction": matches[0]}


async def intact_publication_interactions(pubmed_id: str, limit: Annotated[int, Field(ge=1, le=100)] = 20,
                                          offset: Annotated[int, Field(ge=0, le=1_000_000)] = 0) -> dict:
    """List interactions curated from one PubMed reference."""
    pmid = identifier(pubmed_id, r"[0-9]+", "PubMed ID")
    params = page(limit, offset)
    return await _get(f"interaction/findInteractions/{pmid}%20(pubmed)",
                      {"first": params["offset"], "number": params["limit"]})


TOOLS = (
    intact_interaction_search,
    intact_interactor_search,
    intact_interaction_details,
    intact_publication_interactions,
)


def search_endpoints() -> str:
    """Describe the IntAct search endpoints and paging constraints."""
    return json.dumps({
        "resource": "intact://search-endpoints",
        "base": BASE,
        "endpoints": {
            "intact_interaction_search": "interaction/findInteractions/{query}",
            "intact_interactor_search": "interactor/findInteractor/{query}",
            "intact_interaction_details": "interaction AC pattern EBI-[0-9]+",
            "intact_publication_interactions": "query by PubMed ID",
        },
        "paging": {"first": "0-1000000", "number": "1-100", "mode": "upstream pagination preserved"},
        "query_limit": "300 characters",
    })


RESOURCES = (
    ("intact://search-endpoints", search_endpoints),
)
