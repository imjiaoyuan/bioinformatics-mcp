"""EMDB cryo-EM map entries, resolutions, map files and text search."""
from __future__ import annotations

from typing import Any

from common.api import json_response, page
from common.http import bounded, identifier, text

BASE = "https://www.ebi.ac.uk/emdb/api"


def _id(value: str) -> str:
    return identifier(value.upper(), r"EMD-[0-9]+", "EMDB ID")


async def _get_entry(emdb_id: str) -> tuple[str, dict]:
    data, source = await json_response(f"{BASE}/entry/{_id(emdb_id)}")
    return _id(emdb_id), {**source, **data}


def _value(node: Any) -> Any:
    """Flatten the EMDB valueOf_ convention to plain values."""
    if isinstance(node, dict):
        return node.get("valueOf_", node)
    return node


def _resolutions(data: dict) -> list[dict]:
    entries = []
    for determination in data.get("structure_determination_list", {}).get("structure_determination", []):
        method = determination.get("method")
        for processing in determination.get("image_processing", []):
            reconstruction = processing.get("final_reconstruction", {})
            resolution = reconstruction.get("resolution")
            if resolution is None:
                continue
            entries.append({
                "method": method,
                "resolution": _value(resolution),
                "units": resolution.get("units") if isinstance(resolution, dict) else None,
                "resolution_type": resolution.get("res_type") if isinstance(resolution, dict) else None,
                "resolution_method": reconstruction.get("resolution_method"),
            })
    return entries


def _map_records(data: dict) -> list[dict]:
    records: list[dict] = []
    for kind, node in [("primary_map", data.get("map")), ("segmentation", None)]:
        if kind == "primary_map" and node:
            records.append({"kind": kind, **_map_record(node)})
    for segment in data.get("interpretation", {}).get("segmentation_list", {}).get("segmentation", []):
        records.append({"kind": "segmentation", "file": segment.get("file")})
    for half_map in data.get("interpretation", {}).get("half_map_list", {}).get("half_map", []):
        records.append({"kind": "half_map", **_map_record(half_map)})
    return records


def _map_record(node: dict) -> dict:
    statistics = node.get("statistics", {})
    return {
        "file": node.get("file"),
        "format": node.get("format"),
        "size_kbytes": node.get("size_kbytes"),
        "dimensions": node.get("dimensions"),
        "pixel_spacing": {axis: _value(spacing) for axis, spacing in node.get("pixel_spacing", {}).items()},
        "contour_level": [contour.get("level") for contour in node.get("contour_list", {}).get("contour", [])],
        "statistics": {key: statistics[key] for key in ("average", "minimum", "maximum", "std") if key in statistics},
    }


async def emdb_entry(emdb_id: str) -> dict:
    """Retrieve the full metadata record of one EMDB entry."""
    emdb_id, data = await _get_entry(emdb_id)
    admin = data.get("admin", {})
    return {
        **data,
        "emdb_id": data.get("emdb_id", emdb_id),
        "title": admin.get("title"),
        "status": _value(admin.get("current_status", {}).get("code")),
        "deposition_date": admin.get("key_dates", {}).get("deposition"),
    }


async def emdb_resolution(emdb_id: str) -> dict:
    """Report the author-reported resolution, its method and type for one entry."""
    emdb_id, data = await _get_entry(emdb_id)
    return {**data, "resolutions": _resolutions(data)}


async def emdb_map_files(emdb_id: str) -> dict:
    """List primary map, half map and segmentation file names with sizes and statistics.

    Returns file references only; maps must be downloaded from the EMDB FTP archive.
    """
    emdb_id, data = await _get_entry(emdb_id)
    return {**data, "map_files": _map_records(data)}


async def emdb_search(query: str, limit: int = 10, offset: int = 0) -> dict:
    """Search EMDB entries by free text or fielded queries (e.g. title:"apoferritin").

    Returns trimmed hits with identifiers and resolutions; paging is applied upstream.
    """
    bounded(limit, 100)
    page(limit, offset)
    query = text(query)
    url = f"{BASE}/search/{query}"
    data, source = await json_response(url, {"rows": limit, "start": offset, "wt": "json"})
    hits = data if isinstance(data, list) else data.get("list", [])
    results = []
    for hit in hits:
        admin = hit.get("admin", {})
        results.append({
            "emdb_id": hit.get("emdb_id"),
            "title": admin.get("title"),
            "status": _value(admin.get("current_status", {}).get("code")),
            "release_date": admin.get("key_dates", {}).get("map_release"),
            "resolutions": [entry.get("resolution") for entry in _resolutions(hit)],
            "sample": hit.get("sample", {}).get("name", {}).get("valueOf_"),
        })
    return {**source, "query": query, "limit": limit, "offset": offset, "results": results,
            "total": len(results), "pagination": "upstream"}


TOOLS = (
    emdb_entry,
    emdb_resolution,
    emdb_map_files,
    emdb_search,
)


RESOURCES = ()
