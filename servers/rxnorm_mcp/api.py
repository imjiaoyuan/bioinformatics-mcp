"""RxNorm drug name resolution and concept metadata via the NLM RxNav REST API.

Results come from the public RxNav API (https://rxnav.nlm.nih.gov/REST), part
of the U.S. National Library of Medicine RxNorm vocabulary service. RxNorm is
in the public domain within the U.S. ``umlscui`` fields follow UMLS licence terms.
"""
from __future__ import annotations

from typing import Annotated

from pydantic import Field

from common.api import json_response, local_page, page
from common.http import identifier, text

BASE = "https://rxnav.nlm.nih.gov/REST"

_TTYS = ("IN", "PIN", "MIN", "SCD", "SBD", "GPCK", "BPCK", "PSN", "SCDF", "SCDC")


def _rxcui(value: str) -> str:
    return identifier(value, r"[0-9]+", "RxNorm rxcui")


def _ttys(value: str) -> str:
    parts = [identifier(part.upper(), r"[A-Z]{2,4}", "tty") for part in value.split(",")]
    unknown = [part for part in parts if part not in _TTYS]
    if unknown:
        raise ValueError(f"Unknown tty values: {', '.join(unknown)}; known: {', '.join(_TTYS)}")
    return "+".join(parts)


async def rxnorm_drugs(name: str, limit: Annotated[int, Field(ge=1, le=100)] = 30) -> dict:
    """Resolve a drug name to RxNorm concepts (ingredient, branded and clinical packs/drugs).

    Slices the byte-bounded upstream result locally; concepts are grouped by tty upstream.
    """
    name = text(name, "name", 150)
    paging = page(limit, 0)
    data, source = await json_response(f"{BASE}/drugs", {"name": name}, headers={"Accept": "application/json"})
    group = data.get("drugGroup", {})
    rows = [concept for concept_group in group.get("conceptGroup", [])
            for concept in concept_group.get("conceptProperties", [])]
    return {**source, **local_page(rows, paging["limit"], 0), "name": name}


async def rxnorm_properties(rxcui: str) -> dict:
    """Retrieve one RxNorm concept's name, synonym, term type (tty) and UMLS cross-reference."""
    data, source = await json_response(f"{BASE}/rxcui/{_rxcui(rxcui)}/properties", headers={"Accept": "application/json"})
    properties = data.get("properties")
    if not isinstance(properties, dict):
        raise ValueError(f"No RxNorm properties found for rxcui {rxcui}")
    return {**source, **properties}


async def rxnorm_related(rxcui: str, tty: str = "IN") -> dict:
    """List RxNorm concepts related to one rxcui filtered by term types, e.g. IN,SCD.

    ``tty`` accepts comma-separated RxNorm term types (IN, PIN, SCD, SBD, GPCK, BPCK, ...).
    """
    data, source = await json_response(f"{BASE}/rxcui/{_rxcui(rxcui)}/related", {"tty": _ttys(tty)},
                             headers={"Accept": "application/json"})
    group = data.get("relatedGroup", {})
    rows = [concept for concept_group in group.get("conceptGroup", [])
            for concept in concept_group.get("conceptProperties", [])]
    return {**source, "rxcui": rxcui, "results": rows, "total": len(rows)}


TOOLS = (
    rxnorm_drugs,
    rxnorm_properties,
    rxnorm_related,
)
