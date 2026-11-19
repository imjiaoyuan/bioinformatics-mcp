"""UniChem cross-references between chemical databases by structure.

Maps compound identifiers across source databases (ChEMBL, DrugBank, PubChem,
...) via UniChem connectivity records (https://www.ebi.ac.uk/unichem). Use
``unichem_cross_references`` with an InChIKey to translate one structure into
every source's compound IDs.
"""
from __future__ import annotations

from typing import Annotated, Literal

from pydantic import Field

from common.api import json_response, local_page, page
from common.http import bounded, identifier, text

BASE = "https://www.ebi.ac.uk/unichem"

_CompoundType = Literal["uci", "inchi", "inchikey", "sourceID"]


async def unichem_sources(limit: Annotated[int, Field(ge=1, le=100)] = 50,
                          offset: Annotated[int, Field(ge=0, le=1_000)] = 0) -> dict:
    """List UniChem source databases with UCI counts, descriptions and ID URL patterns."""
    paging = page(limit, offset)
    data, source = await json_response(f"{BASE}/api/v1/sources/")
    rows = data.get("sources", [])
    results = [{"src_id": row.get("srcId"), "name": row.get("name"), "name_long": row.get("nameLong"),
                "uci_count": row.get("UCICount"), "description": row.get("description"),
                "base_id_url": row.get("baseIdUrl")} for row in rows]
    return {**source, **local_page(results, paging["limit"], paging["offset"])}


async def unichem_source(src_id: str) -> dict:
    """Retrieve one UniChem source database by numeric src_id (e.g. 1 for ChEMBL)."""
    src_id = identifier(src_id, r"[0-9]+", "UniChem src_id")
    data, source = await json_response(f"{BASE}/api/v1/sources/{src_id}")
    if not isinstance(data, dict) or data.get("response") != "Success" or not data.get("sources"):
        raise ValueError(f"No UniChem source matches src_id {src_id}")
    row = data["sources"][0]
    return {**source, "src_id": row.get("srcId"), "name": row.get("name"),
            "name_long": row.get("nameLong"), "uci_count": row.get("UCICount"),
            "description": row.get("description"), "base_id_url": row.get("baseIdUrl")}


async def unichem_resolve(compound: str, type_: _CompoundType,
                          source_id: str | None = None) -> dict:
    """Fetch a compound's UCI, InChI and per-source identifiers from one representation.

    ``compound`` is an InChI, InChIKey, UCI or source compound ID; with ``type_``
    ``sourceID`` also pass the UniChem ``source_id`` the identifier belongs to.
    """
    compound = text(compound, "compound", 500)
    body: dict = {"compound": compound, "type": type_}
    if type_ == "sourceID":
        if source_id is None:
            raise ValueError("source_id is required when type_ is 'sourceID'")
        body["sourceID"] = int(identifier(source_id, r"[0-9]+", "UniChem src_id"))
    elif source_id is not None:
        raise ValueError("source_id only applies when type_ is 'sourceID'")
    data, source = await json_response(f"{BASE}/api/v1/compounds", body=body)
    compounds = data.get("compounds") if isinstance(data, dict) else None
    if not compounds:
        raise ValueError(f"No UniChem compound matches {compound} (type {type_})")
    return {**source, "compounds": compounds}


async def unichem_cross_references(inchikey: str) -> dict:
    """Translate one InChIKey into compound IDs across every connected UniChem source."""
    key = identifier(inchikey.upper(), r"[A-Z]{14}-[A-Z]{10}-[A-Z]", "InChIKey")
    data, source = await json_response(f"{BASE}/rest/verbose_inchikey/{key}")
    if not isinstance(data, list):
        raise ValueError(f"No UniChem cross-references match InChIKey {key}")
    references = [{"src_id": row.get("src_id"), "name": row.get("name"),
                   "name_long": row.get("name_long"),
                   "src_compound_ids": row.get("src_compound_id", [])}
                  for row in data if isinstance(row, dict)]
    return {**source, "inchikey": key, "results": references, "total": len(references)}


TOOLS = (
    unichem_sources,
    unichem_source,
    unichem_resolve,
    unichem_cross_references,
)
