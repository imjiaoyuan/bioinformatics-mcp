from __future__ import annotations
import json
import re
from typing import Annotated, Literal

from pydantic import Field

from common.http import bounded, request, text

SEARCH = "https://search.rcsb.org/rcsbsearch/v2/query"
CORE = "https://data.rcsb.org/rest/v1/core"
DOWNLOAD_FORMATS = ("cif", "pdb", "bcif")


def _pdb_id(value: str) -> str:
    value = value.strip()
    if not re.fullmatch(r"[0-9][A-Za-z0-9]{3}", value):
        raise ValueError("pdb_id must be a four-character PDB identifier such as 4HHB")
    return value


async def pdb_search(query: str, max_results: Annotated[int, Field(ge=1, le=100)] = 20) -> dict:
    """Search RCSB PDB by text, gene, protein, ligand, or PDB query syntax."""
    query = text(query)
    max_results = bounded(max_results, 100, "max_results")
    payload = {"query": {"type": "terminal", "service": "full_text", "parameters": {"value": query}},
               "return_type": "entry", "request_options": {"paginate": {"start": 0, "rows": max_results}}}
    data = (await request("POST", SEARCH, json=payload)).json()
    return {"query": query, "total_count": data.get("total_count", 0),
            "entries": [{"pdb_id": x.get("identifier"), "score": x.get("score")} for x in data.get("result_set", [])]}

async def pdb_entry(pdb_id: str) -> dict:
    """Get structured metadata for a PDB entry (for example 4HHB)."""
    pdb_id = _pdb_id(pdb_id).upper()
    return (await request("GET", f"{CORE}/entry/{pdb_id}")).json()

async def pdb_download_url(pdb_id: str, format: Literal["cif", "pdb", "bcif"] = "cif") -> dict:
    """Return an official download URL for PDB/mmCIF/structure files."""
    pdb_id = _pdb_id(pdb_id).lower()
    if format not in DOWNLOAD_FORMATS: raise ValueError("format must be cif, pdb, or bcif")
    return {"pdb_id": pdb_id.upper(), "format": format, "url": f"https://files.rcsb.org/download/{pdb_id}.{format}"}


TOOLS = (
    pdb_search,
    pdb_entry,
    pdb_download_url,
)


def search_scopes() -> str:
    """Describe the search scope, return type and download formats."""
    return json.dumps({
        "resource": "pdb://search-scopes",
        "search": {"service": "full_text", "return_type": "entry",
                   "max_results": "1-100", "query_syntax": "text, gene, protein, ligand or RCSB query syntax"},
        "download_formats": list(DOWNLOAD_FORMATS),
        "pdb_id_pattern": "[0-9][A-Za-z0-9]{3}",
    })


RESOURCES = (
    ("pdb://search-scopes", search_scopes),
)
