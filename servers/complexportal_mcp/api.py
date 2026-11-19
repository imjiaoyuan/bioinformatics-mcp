"""Complex Portal curated macromolecular complexes: search, details and participants.

Results come from the public Complex Portal REST service
(https://www.ebi.ac.uk/complex-portal), maintained by EMBL-EBI as part of the
IntAct suite. Cite the Complex Portal when redistributing its content.
"""
from __future__ import annotations

import json
from typing import Annotated

from pydantic import Field

from common.api import json_response, page
from common.http import identifier, text

BASE = "https://www.ebi.ac.uk/intact/complex-ws"


def _ac(value: str) -> str:
    return identifier(value.upper(), r"CPX-[0-9]+", "Complex Portal AC")


async def _get(path: str, params: dict | None = None) -> dict:
    data, source = await json_response(f"{BASE}/{path}", params)
    return {**source, **data}


async def complexportal_search(query: str, limit: Annotated[int, Field(ge=1, le=100)] = 20,
                               offset: Annotated[int, Field(ge=0, le=1_000_000)] = 0) -> dict:
    """Search curated complexes by name, member gene/protein identifier or function.

    Upstream paging (first/number) is forwarded and totalNumberOfResults is preserved.
    """
    paging = page(limit, offset)
    return await _get(f"search/{text(query, 'query', 300)}",
                      {"first": paging["offset"], "number": paging["limit"]})


async def complexportal_details(complex_ac: str) -> dict:
    """Retrieve one curated complex: stoichiometry, functions, ligands and cross-references."""
    return await _get(f"complex/{_ac(complex_ac)}")


async def complexportal_participants(complex_ac: str) -> dict:
    """List a complex's interactors with identifiers, stoichiometry and biological roles."""
    ac = _ac(complex_ac)
    data = await _get(f"complex/{ac}")
    return {"source_url": data.get("source_url"), "complex_ac": data.get("complexAc", ac),
            "name": data.get("name"), "participants": data.get("participants", [])}


TOOLS = (
    complexportal_search,
    complexportal_details,
    complexportal_participants,
)


def complexportal_endpoints() -> str:
    """Describe Complex Portal endpoints and identifier patterns."""
    return json.dumps({
        "resource": "complexportal://endpoints",
        "base": BASE,
        "endpoints": {
            "complexportal_search": "search/{query}?first={offset}&number={limit}",
            "complexportal_details": "complex/{CPX-N}",
            "complexportal_participants": "complex/{CPX-N} participants projection",
        },
        "identifier_pattern": "CPX-[0-9]+",
        "query_limit": "300 characters",
    })


RESOURCES = (
    ("complexportal://endpoints", complexportal_endpoints),
)
