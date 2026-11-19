"""JASPAR transcription factor binding profiles: search and position frequency matrices.

Results come from the public JASPAR REST API (https://jaspar.elixir.no/api/v1).
JASPAR data is open (CC-BY style terms via jaspar.genereg.net/terms/); cite the
current JASPAR release when redistributing matrices.
"""
from __future__ import annotations

from typing import Annotated

from pydantic import Field

from common.api import json_response, page
from common.http import identifier, text

BASE = "https://jaspar.elixir.no/api/v1"

_SUMMARY_KEYS = ("matrix_id", "base_id", "name", "collection", "tax_group", "species",
                 "family", "class", "pfm", "pubmed_ids", "uniprot_ids", "sequence_logo",
                 "versions_url", "type")


def _matrix_id(value: str) -> str:
    value = value.upper()
    return identifier(value, r"MA[0-9]{4}(\.[0-9]+)?", "JASPAR matrix ID (e.g. MA0049 or MA0049.3)")


async def jaspar_search(search: str | None = None, tax_group: str | None = None,
                        collection: str | None = None,
                        limit: Annotated[int, Field(ge=1, le=100)] = 20,
                        offset: Annotated[int, Field(ge=0, le=1_000_000)] = 0) -> dict:
    """Search TF binding profiles by TF name, matrix ID or free text.

    Optional filters: ``tax_group`` (e.g. vertebrates, plants, insects) and
    ``collection`` (e.g. CORE). Paging combines one upstream page with a local slice.
    """
    params = {"page_size": page(limit, offset)["limit"], "page": offset // limit + 1}
    if search is not None:
        params["search"] = text(search, "search", 200)
    if tax_group is not None:
        params["tax_group"] = identifier(tax_group.lower(), r"[a-z]+", "taxonomic group")
    if collection is not None:
        params["collection"] = identifier(collection.upper(), r"[A-Z_]+", "collection")
    data, source = await json_response(f"{BASE}/matrix/", params)
    rows = data.get("results", [])
    start = offset % params["page_size"]
    sliced = rows[start:start + params["page_size"]]
    count = data.get("count", 0)
    return {**source, "results": sliced, "total": count, "limit": params["page_size"],
            "offset": offset, "truncated": offset + len(sliced) < count,
            "pagination": "upstream page plus local slice"}


async def jaspar_matrix(matrix_id: str) -> dict:
    """Retrieve one binding profile: metadata and the position frequency matrix (PFM).

    Bare base IDs (``MA0049``) resolve to the latest release version.
    """
    data, source = await json_response(f"{BASE}/matrix/{_matrix_id(matrix_id)}/")
    if "matrix_id" not in data:
        raise ValueError(f"No JASPAR matrix matches {matrix_id.upper()} in the current release")
    return {**source, **{key: data[key] for key in _SUMMARY_KEYS if key in data}}


TOOLS = (
    jaspar_search,
    jaspar_matrix,
)
