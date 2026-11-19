"""MGnify (EBI metagenomics) studies, biomes and analyses via the JSON:API v1.

Results come from the public MGnify REST API
(https://www.ebi.ac.uk/metagenomics/api/v1). MGnify analysis outputs are
CC-BY / CC0 as per study metadata; cite studies when redistributing.
"""
from __future__ import annotations

from typing import Annotated

from pydantic import Field

from common.api import json_response
from common.http import bounded, identifier

BASE = "https://www.ebi.ac.uk/metagenomics/api/v1"


def _accession(value: str, name: str = "MGnify accession") -> str:
    return identifier(value.upper(), r"MGY[SA][0-9]+", name)


def _lineage(value: str) -> str:
    return identifier(value, r"root(:[A-Za-z0-9-]+)*", "MGnify biome lineage")


async def _get(path: str, params: dict | None = None) -> tuple[dict, dict]:
    data, source = await json_response(f"{BASE}/{path}", params)
    if isinstance(data, dict) and data.get("errors"):
        raise ValueError(f"MGnify returned no match for {path}")
    return data, source


def _rows(data: dict) -> list:
    rows = data.get("data", [])
    return rows if isinstance(rows, list) else []


def _page(data: dict, page_index: int, page_size: int) -> dict:
    meta = data.get("meta", {})
    if isinstance(meta, dict) and isinstance(meta.get("pagination"), dict):
        info = meta["pagination"]
        return {"count": info.get("count"), "page": page_index, "page_size": page_size,
                "pages": info.get("pages")}
    return {"page": page_index, "page_size": page_size}


async def mgnify_studies(lineage: str = "root",
                         page_index: Annotated[int, Field(ge=1, le=500)] = 1,
                         page_size: Annotated[int, Field(ge=1, le=100)] = 20) -> dict:
    """List metagenomic studies under one biome lineage (e.g. root:Environmental:Air)."""
    data, source = await _get("studies", {"lineage": _lineage(lineage),
                                          "page": bounded(page_index, 500, "page_index", 1),
                                          "page_size": bounded(page_size, 100)})
    results = [{"accession": row["attributes"].get("accession"),
                "name": row["attributes"].get("study-name"),
                "abstract": row["attributes"].get("study-abstract"),
                "samples_count": row["attributes"].get("samples-count"),
                "centre_name": row["attributes"].get("centre-name"),
                "bioproject": row["attributes"].get("bioproject")} for row in _rows(data)]
    return {**source, "results": results, **_page(data, page_index, page_size)}


async def mgnify_study(accession: str) -> dict:
    """Retrieve one study's metadata: abstract, biome relationships and sample counts."""
    data, source = await _get(f"studies/{_accession(accession)}")
    row = data.get("data", {})
    attributes = row.get("attributes", {})
    return {**source, "accession": attributes.get("accession"),
            "name": attributes.get("study-name"), "abstract": attributes.get("study-abstract"),
            "samples_count": attributes.get("samples-count"),
            "centre_name": attributes.get("centre-name"), "bioproject": attributes.get("bioproject")}


async def mgnify_analyses(study_accession: str,
                          page_index: Annotated[int, Field(ge=1, le=500)] = 1,
                          page_size: Annotated[int, Field(ge=1, le=100)] = 20) -> dict:
    """List completed analyses for one study: pipeline version, experiment type and instrument."""
    data, source = await _get("analyses", {"study_accession": _accession(study_accession, "study accession"),
                                           "page": bounded(page_index, 500, "page_index", 1),
                                           "page_size": bounded(page_size, 100)})
    results = [{"accession": row["attributes"].get("accession"),
                "status": row["attributes"].get("analysis-status"),
                "experiment_type": row["attributes"].get("experiment-type"),
                "instrument_platform": row["attributes"].get("instrument-platform"),
                "instrument_model": row["attributes"].get("instrument-model"),
                "pipeline_version": row["attributes"].get("pipeline-version"),
                "complete_time": row["attributes"].get("complete-time")} for row in _rows(data)]
    return {**source, "results": results, **_page(data, page_index, page_size)}


async def mgnify_biome(lineage: str) -> dict:
    """Retrieve one biome node's lineage, name and sample count (e.g. root:Host-associated:Human)."""
    data, source = await _get(f"biomes/{_lineage(lineage)}")
    row = data.get("data", {})
    attributes = row.get("attributes", {})
    return {**source, "id": row.get("id"), "biome_name": attributes.get("biome-name"),
            "lineage": attributes.get("lineage"), "samples_count": attributes.get("samples-count")}


TOOLS = (
    mgnify_studies,
    mgnify_study,
    mgnify_analyses,
    mgnify_biome,
)
