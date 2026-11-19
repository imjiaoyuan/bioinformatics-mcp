"""RNAcentral non-coding RNA sequences, metadata and literature references.

Entries come from the public RNAcentral REST API (https://rnacentral.org/api);
free-text search uses the EBI Search RNAcentral domain. RNAcentral content is
distributed under CC0; cite the database when redistributing results.
"""
from __future__ import annotations

from typing import Annotated

from pydantic import Field

from common.api import json_response, local_page, page
from common.http import identifier, text

API = "https://rnacentral.org/api/v1"
SEARCH = "https://www.ebi.ac.uk/ebisearch/ws/rest/rnacentral"

Sequence = Annotated[str, Field(description="RNAcentral URS identifier, e.g. URS000075800A")]


def _urs(value: str) -> str:
    return identifier(value.upper(), r"URS[0-9A-F]{10}", "RNAcentral URS identifier")


async def rnacentral_search(query: str, limit: Annotated[int, Field(ge=1, le=100)] = 20,
                            offset: Annotated[int, Field(ge=0, le=1_000_000)] = 0) -> dict:
    """Search RNAcentral sequences by gene name, RNA type or free text via EBI Search.

    Species-specific search identifiers (``URS..._taxid``) are normalized to bare URS ids.
    """
    paging = page(limit, offset)
    data, source = await json_response(f"{SEARCH}/", {"query": text(query, "query", 300),
                                                      "format": "json", "size": paging["limit"],
                                                      "start": paging["offset"]})
    hits = [{"urs": entry["id"].split("_")[0], "search_id": entry["id"],
             "entry_url": f"https://rnacentral.org/entry/{entry['id'].split('_')[0]}"}
            for entry in data.get("entries", [])]
    return {**source, "hit_count": data.get("hitCount", 0), "results": hits,
            "limit": paging["limit"], "offset": paging["offset"],
            "truncated": offset + limit < data.get("hitCount", 0),
            "pagination": "upstream start/size"}


async def rnacentral_entry(urs: Sequence) -> dict:
    """Retrieve one RNAcentral sequence entry with rna_type, description and database cross-references."""
    return await _entry(urs)


async def rnacentral_sequence(urs: Sequence) -> dict:
    """Retrieve a sequence's nucleotides, length, RNA type and organism counts."""
    entry = await _entry(urs)
    keys = ("rnacentral_id", "sequence", "length", "rna_type", "description",
            "count_distinct_organisms", "distinct_databases", "is_active")
    return {key: entry[key] for key in keys if key in entry} | {
        "source_url": entry.get("source_url"), "entry_url": entry.get("url")}


async def rnacentral_publications(urs: Sequence, limit: Annotated[int, Field(ge=1, le=100)] = 20) -> dict:
    """List literature references associated with one RNAcentral entry."""
    data, source = await json_response(f"{API}/rna/{_urs(urs)}/publications")
    return {**source, **local_page(data.get("results", []), limit, 0),
            "total": data.get("count", len(data.get("results", [])))}


async def _entry(urs: str) -> dict:
    data, source = await json_response(f"{API}/rna/{_urs(urs)}")
    if not isinstance(data, dict) or "rnacentral_id" not in data:
        raise ValueError("Unexpected RNAcentral response format")
    return {**source, **data}


TOOLS = (
    rnacentral_search,
    rnacentral_entry,
    rnacentral_sequence,
    rnacentral_publications,
)
