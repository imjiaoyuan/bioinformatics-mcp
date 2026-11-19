"""PRIDE proteomics data repository: keyword search and project metadata.

Queries the public PRIDE archive REST API v2
(https://www.ebi.ac.uk/pride/ws/archive/v2). Dataset reuse follows each
project's licence (see the license field of project details).
"""
from __future__ import annotations

from typing import Annotated

from pydantic import Field

from common.api import json_response, local_page, page
from common.http import identifier, text

BASE = "https://www.ebi.ac.uk/pride/ws/archive/v2"


def _accession(value: str) -> str:
    return identifier(value.upper(), r"PXD[0-9]+", "PRIDE accession")


async def pride_search_projects(keyword: str,
                                limit: Annotated[int, Field(ge=1, le=100)] = 20,
                                offset: Annotated[int, Field(ge=0, le=1_000_000)] = 0) -> dict:
    """Search PRIDE mass spectrometry projects by keyword (title, description, keywords).

    Paging combines one upstream page (pageSize) with a local slice; the upstream
    search caps its result list, so counts beyond it are not reported.
    """
    keyword = text(keyword, "keyword", 200)
    paging = page(limit, offset)
    data, source = await json_response(f"{BASE}/search/projects", {
        "keyword": keyword, "pageSize": paging["limit"], "page": offset // limit + 1})
    rows = data if isinstance(data, list) else []
    start = offset % paging["limit"]
    results = [{"accession": row.get("accession"), "title": row.get("title"),
                "description": (row.get("projectDescription") or "")[:300],
                "publication_date": row.get("publicationDate"),
                "keywords": row.get("keywords")} for row in rows[start:start + paging["limit"]]]
    return {**source, "results": results, "keyword": keyword, "limit": paging["limit"],
            "offset": offset, "returned": len(results), "pagination": "upstream page plus local slice"}


async def pride_project(accession: str) -> dict:
    """Retrieve one PRIDE project: description, DOI, organisms, instruments and licence."""
    data, source = await json_response(f"{BASE}/projects/{_accession(accession)}")
    if not isinstance(data, dict) or data.get("accession") != _accession(accession):
        raise ValueError(f"No PRIDE project matches {_accession(accession)}")
    keys = ("accession", "title", "projectDescription", "doi", "publicationDate",
            "organisms", "instruments", "experimentTypes", "keywords", "labPIs",
            "countries", "license", "identifiedPTMStrings")
    return {**source, **{key: data[key] for key in keys if key in data}}


TOOLS = (
    pride_search_projects,
    pride_project,
)
