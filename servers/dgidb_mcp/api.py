"""DGIdb drug-gene interactions via the Drug Gene Interaction Database GraphQL API.

Queries https://dgidb.org/api/graphql (DGIdb v5, no auth). Interaction scores
aggregate evidence from ChEMBL, DrugBank-derived claims, Ensembl and others;
check DGIdb source attributions before clinical use.
"""
from __future__ import annotations

from typing import Annotated

from pydantic import Field

from common.api import json_response
from common.http import bounded, identifiers

BASE = "https://dgidb.org/api/graphql"


async def _query(selection: str, declaration: str, variables: dict) -> dict:
    result, source = await json_response(
        BASE, body={"query": f"query({declaration}) {{ {selection} }}", "variables": variables})
    errors = result.get("errors") if isinstance(result, dict) else None
    if errors:
        message = errors[0].get("message", "unknown DGIdb error") if isinstance(errors[0], dict) else str(errors[0])
        raise ValueError(f"DGIdb query failed: {message}")
    return {**source, "data": result.get("data") if isinstance(result, dict) else None}


async def dgidb_genes(names: list[str], first: Annotated[int, Field(ge=1, le=100)] = 20) -> dict:
    """Look up genes by symbol and return their drug interactions with scores and sources.

    ``names`` accepts 1-10 gene symbols (e.g. ``BRAF``, ``EGFR``); ``first`` bounds
    the interactions fetched per gene.
    """
    symbols = identifiers(names, 10)
    bounded(first)
    return await _query("genes(names: $n, first: $f) {nodes{name longName "
                        "interactions{interactionScore drug{name} sources{sourceDbName}}}}",
                        "$n: [String!]!, $f: Int!", {"n": [s.upper() for s in symbols], "f": first})


async def dgidb_drugs(names: list[str], first: Annotated[int, Field(ge=1, le=100)] = 20) -> dict:
    """Look up drugs by name and return the genes they interact with, with scores.

    ``names`` accepts 1-10 drug names or concepts (e.g. ``imatinib``).
    """
    drug_names = identifiers(names, 10)
    bounded(first)
    return await _query("drugs(names: $n, first: $f) {nodes{name conceptId approved "
                        "interactions{interactionScore gene{name}}}}",
                        "$n: [String!]!, $f: Int!", {"n": drug_names, "f": first})


async def dgidb_gene_matches(search_terms: list[str],
                             first: Annotated[int, Field(ge=1, le=100)] = 20) -> dict:
    """Fuzzy-match partial gene names against DGIdb (useful to resolve symbols before lookup)."""
    terms = identifiers(search_terms, 10)
    bounded(first)
    return await _query("geneMatches(searchTerms: $q) {noMatches{searchTerm} "
                        "directMatches{searchTerm matchType matches{name longName}}}",
                        "$q: [String!]!", {"q": terms})


TOOLS = (
    dgidb_genes,
    dgidb_drugs,
    dgidb_gene_matches,
)
