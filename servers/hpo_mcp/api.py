"""Human Phenotype Ontology terms, search and hierarchy via the JAX ontology service."""
from __future__ import annotations

import re
from typing import Annotated

from pydantic import Field

from common.api import json_response, local_page
from common.http import bounded, identifier, identifiers, text

BASE = "https://ontology.jax.org/api/hp"
_SEARCH_PATTERN = re.compile(r"[a-zA-Z0-9\s\-':,]+")

Limit = Annotated[int, Field(ge=1, le=100)]
PageIndex = Annotated[int, Field(ge=0, le=10_000)]


def _term_id(value: str) -> str:
    return identifier(value.upper(), r"HP:[0-9]{7}", "HPO term ID")


def _search_query(value: str) -> str:
    value = text(value, "query", 250)
    if len(value) < 3 or not _SEARCH_PATTERN.fullmatch(value):
        raise ValueError("query must contain 3-250 characters matching the upstream search pattern")
    return value


async def _get(path: str, params: dict | None = None) -> tuple[dict | list, dict]:
    return await json_response(f"{BASE}{path}", params)


async def hpo_search(query: str, limit: Limit = 20, page: PageIndex = 0) -> dict:
    """Search HPO terms by name, ID fragment or synonym; returns upstream pagination metadata."""
    data, source = await _get("/search", {
        "q": _search_query(query),
        "page": bounded(page, 10_000, "page", 0),
        "limit": bounded(limit, 100),
    })
    return {**source, **data}


async def hpo_term(term_id: str) -> dict:
    """Retrieve one HPO term with definition, synonyms, cross-references and translations."""
    data, source = await _get(f"/terms/{_term_id(term_id)}")
    if not data:
        raise ValueError(f"HPO term not found: {term_id}")
    return {**source, **data}


async def hpo_terms(term_ids: list[str]) -> dict:
    """Retrieve multiple HPO terms at once by a list of HP:XXXXXXX identifiers."""
    filter_value = ",".join(_term_id(value) for value in identifiers(term_ids, 100))
    data, source = await _get("/terms", {"filter": filter_value})
    return local_page(list(data), 100, 0, **source)


async def hpo_children(term_id: str) -> dict:
    """List the direct children of an HPO term."""
    data, source = await _get(f"/terms/{_term_id(term_id)}/children")
    return local_page(list(data), 100, 0, term_id=_term_id(term_id), **source)


async def hpo_parents(term_id: str) -> dict:
    """List the direct parents of an HPO term."""
    data, source = await _get(f"/terms/{_term_id(term_id)}/parents")
    return local_page(list(data), 100, 0, term_id=_term_id(term_id), **source)


async def hpo_ancestors(term_id: str) -> dict:
    """List all ancestors of an HPO term up to the root."""
    data, source = await _get(f"/terms/{_term_id(term_id)}/ancestors")
    return local_page(list(data), 100, 0, term_id=_term_id(term_id), **source)


async def hpo_descendants(term_id: str) -> dict:
    """List all descendants below an HPO term."""
    data, source = await _get(f"/terms/{_term_id(term_id)}/descendants")
    return local_page(list(data), 100, 0, term_id=_term_id(term_id), **source)


TOOLS = (
    hpo_search,
    hpo_term,
    hpo_terms,
    hpo_children,
    hpo_parents,
    hpo_ancestors,
    hpo_descendants,
)


def hpo_constraints() -> dict:
    """Describe the HPO ontology-service endpoints and identifier/search conventions."""
    return {"base": BASE,
            "term_id": "HP:0000000-style identifier (HP: + 7 digits)",
            "search_query": "3-250 characters of letters, digits, spaces, - ' : ,",
            "endpoints": ["/search", "/terms/{term_id}", "/terms",
                          "/terms/{term_id}/children", "/terms/{term_id}/parents",
                          "/terms/{term_id}/ancestors", "/terms/{term_id}/descendants"],
            "paging": {"search": "limit 1-100, page 0-10000 (upstream pagination)",
                       "hierarchy": "full result set returned, sliced locally"}}


RESOURCES = (
    ("hpo://constraints", hpo_constraints),
)
