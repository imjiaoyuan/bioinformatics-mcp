"""BV-BRC (PATRIC) pathogen genomes: search, genome metadata and coding features.

Queries the public BV-BRC data API (https://www.bv-brc.org/api) with RQL-style
query expressions over its Solr-backed resources. BV-BRC is funded by NIH and
its data are publicly released; cite genome sources when redistributing.
"""
from __future__ import annotations

from typing import Annotated
from urllib.parse import quote

from pydantic import Field

from common.api import json_response, local_page, page
from common.http import bounded, identifier, text

BASE = "https://www.bv-brc.org/api"

_GENOME_KEYS = ("genome_id", "genome_name", "species", "taxon_id", "genome_status",
                "assembly_accession", "bioproject_accession", "biosample_accession",
                "genome_length", "cds", "strain", "collection_date")
_FEATURE_KEYS = ("feature_id", "genome_id", "genome_name", "feature_type", "accession",
                 "start", "end", "strand", "product", "aa_length", "na_length", "go")


def _genome_id(value: str) -> str:
    return identifier(value, r"[0-9]+\.[0-9]+", "BV-BRC genome ID (e.g. 208224.13)")


def _keyword(value: str) -> str:
    value = identifier(value.strip(), r"[A-Za-z0-9][A-Za-z0-9 _.-]*", "search term")
    return quote(value)


async def _rql(resource: str, expression: str, fetch_size: int) -> tuple[dict, dict]:
    # The upstream API rejects start() offsets; fetch a bounded window and slice locally.
    data, source = await json_response(f"{BASE}/{resource}/?{expression}&limit({fetch_size})")
    if not isinstance(data, list):
        raise ValueError("Unexpected BV-BRC response format")
    return data, source


async def bvbrc_genome_search(query: str, limit: Annotated[int, Field(ge=1, le=100)] = 20,
                              offset: Annotated[int, Field(ge=0, le=1_000_000)] = 0) -> dict:
    """Search BV-BRC genomes by name keyword (e.g. ``tuberculosis``, ``Escherichia coli K-12``).

    The upstream window is capped at 1000 rows; paging slices within it.
    """
    paging = page(limit, offset)
    fetch = bounded(offset + limit, 1000, "offset+limit", 1)
    rows, source = await _rql("genome", f"keyword(genome_name,{_keyword(query)})", fetch)
    results = [{key: row[key] for key in _GENOME_KEYS if key in row} for row in rows]
    return {**source, **local_page(results, paging["limit"], paging["offset"]), "query": query}


async def bvbrc_genome(genome_id: str) -> dict:
    """Retrieve one genome record: taxonomy, assembly, status and annotation statistics."""
    gid = _genome_id(genome_id)
    rows, source = await _rql("genome", f"eq(genome_id,{quote(gid)})", 1)
    if not rows:
        raise ValueError(f"No BV-BRC genome matches {gid}")
    return {**source, **{key: rows[0][key] for key in _GENOME_KEYS if key in rows[0]}}


async def bvbrc_features(genome_id: str, limit: Annotated[int, Field(ge=1, le=100)] = 20,
                         offset: Annotated[int, Field(ge=0, le=1_000_000)] = 0) -> dict:
    """List coding features of one genome with locations, products and GO annotations.

    The upstream window is capped at 1000 features; paging slices within it.
    """
    gid = _genome_id(genome_id)
    paging = page(limit, offset)
    fetch = bounded(offset + limit, 1000, "offset+limit", 1)
    rows, source = await _rql("genome_feature", f"eq(genome_id,{quote(gid)})", fetch)
    results = [{key: row[key] for key in _FEATURE_KEYS if key in row} for row in rows]
    return {**source, **local_page(results, paging["limit"], paging["offset"]), "genome_id": gid}


TOOLS = (
    bvbrc_genome_search,
    bvbrc_genome,
    bvbrc_features,
)
