"""Ontology Lookup Service (OLS4): unified term search across EMBL-EBI ontologies.

One entry point for dozens of ontologies (EFO, ChEBI, Orphanet, MP, VT, EDAM,
...). Results come from the public OLS4 REST API
(https://www.ebi.ac.uk/ols4); ontology content keeps its upstream licences.
"""
from __future__ import annotations

from typing import Annotated
from urllib.parse import quote

from pydantic import Field

from common.api import json_response, local_page, page
from common.http import bounded, identifier, text

BASE = "https://www.ebi.ac.uk/ols4/api"


def _ontology(value: str) -> str:
    return identifier(value.lower(), r"[a-z0-9_]+", "ontology id")


def _iri(value: str) -> str:
    value = text(value, "iri", 500)
    if not value.startswith(("http://", "https://")):
        raise ValueError("iri must be an http(s) URI")
    return value


async def _hal_terms(path: str, params: dict | None = None) -> tuple[list, dict]:
    data, source = await json_response(f"{BASE}/{path}", params)
    embedded = data.get("_embedded", {})
    return next(iter(embedded.values()), []), source


async def ols_search(query: str, ontology: str | None = None,
                     limit: Annotated[int, Field(ge=1, le=100)] = 20,
                     offset: Annotated[int, Field(ge=0, le=1_000_000)] = 0) -> dict:
    """Search term labels, synonyms and descriptions across all loaded ontologies.

    Optionally restrict to one ontology id (e.g. ``efo``, ``chebi``, ``orphanet``).
    """
    paging = page(limit, offset)
    params = {"q": text(query, "query", 300), "size": paging["limit"], "start": paging["offset"]}
    if ontology is not None:
        params["ontology"] = _ontology(ontology)
    data, source = await json_response(f"{BASE}/search", params)
    response = data.get("response", {})
    results = [{"iri": doc.get("iri"), "label": doc.get("label"),
                "description": (doc.get("description") or [None])[0],
                "obo_id": doc.get("obo_id"), "ontology": doc.get("ontology_name"),
                "prefix": doc.get("ontology_prefix"), "type": doc.get("type")}
               for doc in response.get("docs", [])]
    return {**source, "hit_count": response.get("numFound", 0), "results": results,
            "limit": paging["limit"], "offset": paging["offset"],
            "pagination": "upstream start/size"}


async def ols_ontologies(limit: Annotated[int, Field(ge=1, le=200)] = 50,
                         page_index: Annotated[int, Field(ge=0, le=200)] = 0) -> dict:
    """List ontologies loaded in OLS with identifiers, titles and preferred prefixes."""
    data, source = await json_response(f"{BASE}/ontologies",
                                       {"size": bounded(limit), "page": bounded(page_index, 200, "page_index", 0)})
    rows = data.get("_embedded", {}).get("ontologies", [])
    results = [{"id": row.get("ontologyId"), "title": row.get("title"),
                "prefix": (row.get("config") or {}).get("preferredPrefix"),
                "description": (row.get("config") or {}).get("description"),
                "version": (row.get("config") or {}).get("version")} for row in rows]
    info = data.get("page", {})
    return {**source, "results": results, "limit": bounded(limit), "page": page_index,
            "total": info.get("totalElements", len(results)), "pagination": "upstream page index"}


async def ols_term(ontology: str, iri: str) -> dict:
    """Fetch one ontology term by its full IRI: label, definition, obsolescence and annotations."""
    terms, source = await _hal_terms(f"ontologies/{_ontology(ontology)}/terms", {"iri": _iri(iri)})
    if not terms:
        raise ValueError(f"No OLS term matches {iri} in {_ontology(ontology)}")
    return {**source, **terms[0]}


async def ols_ancestors(ontology: str, iri: str, limit: Annotated[int, Field(ge=1, le=100)] = 50,
                        offset: Annotated[int, Field(ge=0, le=1_000_000)] = 0) -> dict:
    """List the ancestor terms above one term in the ontology hierarchy."""
    terms, source = await _hal_terms(f"ontologies/{_ontology(ontology)}/terms/"
                                     f"{quote(quote(_iri(iri), safe=''), safe='')}/ancestors")
    return {**source, **local_page(terms, limit, offset)}


async def ols_children(ontology: str, iri: str, limit: Annotated[int, Field(ge=1, le=100)] = 50,
                       offset: Annotated[int, Field(ge=0, le=1_000_000)] = 0) -> dict:
    """List the direct child terms below one term in the ontology hierarchy."""
    terms, source = await _hal_terms(f"ontologies/{_ontology(ontology)}/terms/"
                                     f"{quote(quote(_iri(iri), safe=''), safe='')}/children")
    return {**source, **local_page(terms, limit, offset)}


TOOLS = (
    ols_search,
    ols_ontologies,
    ols_term,
    ols_ancestors,
    ols_children,
)
