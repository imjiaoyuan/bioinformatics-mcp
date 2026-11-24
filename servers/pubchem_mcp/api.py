"""PubChem compounds, substances, assays and annotations (PUG REST + PUG-View)."""
from __future__ import annotations

import re
from typing import Annotated

import httpx
from pydantic import Field

from common.api import json_response, local_page, page
from common.http import identifier, request, safe_url, text

PUG = "https://pubchem.ncbi.nlm.nih.gov/rest/pug"
PUG_VIEW = "https://pubchem.ncbi.nlm.nih.gov/rest/pug_view/data"
PROPERTIES = ("MolecularFormula,MolecularWeight,CanonicalSMILES,IsomericSMILES,"
              "IUPACName,InChI,InChIKey,XLogP,ExactMass,TPSA")


def _cid(value: str) -> str:
    value = identifier(value, r"[0-9]+", "CID")
    if not (1 <= int(value) <= 10_000_000_000):
        raise ValueError("CID must be a positive integer")
    return value


def _numeric(value: str, name: str) -> str:
    value = identifier(value, r"[0-9]+", name)
    if not (1 <= int(value) <= 10_000_000_000):
        raise ValueError(f"{name} must be a positive integer")
    return value


async def _get(url: str, params: dict | None = None, max_bytes: int = 8_000_000) -> dict:
    """Fetch JSON, mapping HTTP errors and PUG Fault bodies to explicit errors."""
    try:
        data, source = await json_response(url, params, max_bytes=max_bytes)
    except httpx.HTTPStatusError as exc:
        status = exc.response.status_code
        if status == 404:
            raise ValueError("PubChem: no record found for this identifier") from None
        if status == 400:
            raise ValueError("PubChem rejected the request: check the identifier or heading") from None
        raise
    if isinstance(data, dict) and "Fault" in data:
        fault = data["Fault"]
        details = "; ".join(str(item) for item in fault.get("Details", []))
        message = f"PubChem {fault.get('Code', 'Error')}: {fault.get('Message', 'request failed')}"
        if details:
            message = f"{message} ({details})"
        raise ValueError(message)
    return {**source, **data}


async def pubchem_resolve(name: str) -> dict:
    """Resolve a compound name to PubChem CID(s); returns every matching CID."""
    text(name, "name", 200)
    data = await _get(f"{PUG}/compound/name/{name}/cids/JSON")
    cids = data.get("IdentifierList", {}).get("CID", [])
    return {**data, "cids": cids, "source_name": name}


async def pubchem_compound(cid: str) -> dict:
    """Retrieve computed properties for one CID (formula, weight, SMILES, InChI, XLogP, TPSA, masses)."""
    data = await _get(f"{PUG}/compound/cid/{_cid(cid)}/property/{PROPERTIES}/JSON")
    rows = data.get("PropertyTable", {}).get("Properties", [])
    return {**data, "compound": rows[0] if rows else None}


async def pubchem_synonyms(cid: str, limit: Annotated[int, Field(ge=1, le=100)] = 20,
                           offset: Annotated[int, Field(ge=0, le=1_000_000)] = 0) -> dict:
    """List known names, trade names and CAS-style synonyms for one CID; paginated locally."""
    page(limit, offset)
    data = await _get(f"{PUG}/compound/cid/{_cid(cid)}/synonyms/JSON")
    info = data.get("InformationList", {}).get("Information", [])
    synonyms = info[0].get("Synonym", []) if info else []
    return local_page(synonyms, limit, offset, cid=int(_cid(cid)), source_url=data["source_url"],
                      pagination="local")


async def pubchem_description(name_or_cid: str) -> dict:
    """Retrieve the title and deposited descriptions (with sources) for a compound name or CID."""
    value = text(name_or_cid, "name_or_cid", 200)
    path = f"cid/{_cid(value)}" if re.fullmatch(r"[0-9]+", value) else f"name/{value}"
    data = await _get(f"{PUG}/compound/{path}/description/JSON")
    entries = data.get("InformationList", {}).get("Information", [])
    return {**data, "entries": entries, "descriptions": len(entries)}


async def pubchem_substance(sid: str) -> dict:
    """Retrieve a deposited PubChem substance record (source, synonyms, associate compounds)."""
    data = await _get(f"{PUG}/substance/sid/{_numeric(sid, 'SID')}/JSON")
    rows = data.get("PC_Substances", [])
    return {**data, "substance": rows[0] if rows else None}


async def pubchem_aid(aid: str) -> dict:
    """Retrieve a bioassay description (title, protocol summary, source, target) via the description endpoint.

    The full /assay/aid/{aid}/JSON record is deprecated for large assays, so only the
    description view is exposed.
    """
    data = await _get(f"{PUG}/assay/aid/{_numeric(aid, 'AID')}/description/JSON")
    rows = data.get("PC_AssayContainer", [])
    return {**data, "assay": rows}


async def pubchem_annotation(cid: str, heading: str = "Pharmacology") -> dict:
    """Retrieve one curated PUG-View annotation section (e.g. Pharmacology, Drug Warnings) for a CID.

    Requests are narrowed to a single heading to keep responses small; see
    https://pubchem.ncbi.nlm.nih.gov/docs/pug-view for available headings.
    """
    heading = text(heading, "heading", 100)
    url = f"{PUG_VIEW}/compound/{_cid(cid)}/JSON"
    response = await request("GET", url, params={"heading": heading}, max_bytes=2_000_000)
    try:
        data = response.json()
    except ValueError:
        raise ValueError("PubChem: unknown heading for this compound") from None
    sections = data.get("Record", {}).get("Section", [])
    extracted = []
    for section in sections:
        for item in section.get("Information", []) or []:
            strings = [part.get("String") for part in item.get("Value", {}).get("StringWithMarkup", [])]
            strings = [part for part in strings if part]
            if strings or item.get("Description"):
                extracted.append({"heading": section.get("TOCHeading", heading),
                                  "description": item.get("Description"),
                                  "text": "\n".join(strings) if strings else None})
    return {"cid": int(_cid(cid)), "heading": heading, "sections": extracted,
            "record_title": data.get("Record", {}).get("RecordTitle"),
            "source_url": safe_url(response.url)}


TOOLS = (
    pubchem_resolve,
    pubchem_compound,
    pubchem_synonyms,
    pubchem_description,
    pubchem_substance,
    pubchem_aid,
    pubchem_annotation,
)


def resource_catalog() -> dict:
    """List PubChem computed properties and endpoint constraints."""
    return {"computed_properties": PROPERTIES.split(","),
            "endpoints": {"resolve": "compound/name/{name}/cids", "compound": "compound/cid/{cid}",
                          "synonyms": "compound/cid/{cid}/synonyms", "description": "compound/.../description",
                          "substance": "substance/sid/{sid}", "assay": "assay/aid/{aid}/description",
                          "annotation": "pug_view compound/{cid}?heading=..."},
            "limit": "1-100", "offset": "0-1000000",
            "id_bounds": "positive integers up to 10000000000"}


RESOURCES = (
    ("pubchem://databases", resource_catalog),
)
