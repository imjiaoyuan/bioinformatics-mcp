"""BioStudies study search, associated files and ArrayExpress SDRF sample annotations."""
from __future__ import annotations

import csv
import io
from itertools import islice
from pathlib import PurePosixPath
from typing import Annotated, Literal
from urllib.parse import quote, urlencode

from pydantic import Field

from common.http import bounded, get_json, identifier, request, text

BASE = "https://www.ebi.ac.uk/biostudies"


def _accession(value: str) -> str:
    return identifier(value.upper(), r"(?:E-[A-Z]+-[0-9]+|S-[A-Z]+[0-9]+)", "BioStudies accession")


async def _study(accession: str) -> dict:
    return await get_json(f"{BASE}/api/v1/studies/{_accession(accession)}")


def _files(study: dict, accession: str) -> list[dict]:
    pending = [study]
    files: dict[str, dict] = {}
    while pending:
        node = pending.pop()
        if isinstance(node, list):
            pending.extend(reversed(node))
        elif isinstance(node, dict):
            path = node.get("path")
            if node.get("type") == "file" and isinstance(path, str):
                if PurePosixPath(path).is_absolute() or ".." in PurePosixPath(path).parts or "\\" in path:
                    raise ValueError("Study contains an unsafe file path")
                files[path] = {**node, "url": f"{BASE}/files/{accession}/{quote(path, safe='/')}"}
            else:
                pending.extend(reversed(list(node.values())))
    return list(files.values())


async def biostudies_search(query: str,
                            collection: Literal["arrayexpress", "all"] = "arrayexpress",
                            limit: Annotated[int, Field(ge=1, le=100)] = 20,
                            page: Annotated[int, Field(ge=1, le=1000)] = 1) -> dict:
    """Search ArrayExpress by default, or all public BioStudies using collection='all'."""
    if collection not in {"arrayexpress", "all"}:
        raise ValueError("collection must be arrayexpress or all")
    path = "search" if collection == "all" else "arrayexpress/search"
    params = {"query": text(query), "pageSize": bounded(limit), "page": bounded(page, 1000, "page")}
    data = await get_json(f"{BASE}/api/v1/{path}", params)
    return {**data, "source_url": f"{BASE}/api/v1/{path}?{urlencode(params)}"}


async def biostudies_record(accession: str) -> dict:
    """Get the study tree, preserving study attributes, sections and external ENA links."""
    accession = _accession(accession)
    return {"study": await _study(accession), "source_url": f"{BASE}/studies/{accession}"}


async def biostudies_files(accession: str, limit: Annotated[int, Field(ge=1, le=200)] = 50,
                           offset: Annotated[int, Field(ge=0, le=100000)] = 0) -> dict:
    """List files from nested study sections, including processed data and IDF/SDRF files."""
    accession = _accession(accession)
    bounded(limit, 200)
    bounded(offset, 100000, "offset", 0)
    files = _files(await _study(accession), accession)
    return {"limit": limit, "offset": offset, "files": files[offset:offset + limit],
            "total": len(files),
            "truncated": offset + limit < len(files),
            "next_offset": offset + limit if offset + limit < len(files) else None,
            "pagination": "local", "source_url": f"{BASE}/studies/{accession}"}


async def biostudies_samples(accession: str, limit: Annotated[int, Field(ge=1, le=200)] = 20) -> dict:
    """Read bounded SDRF assay rows. Columns are separate from rows to preserve duplicate headers."""
    accession = _accession(accession)
    bounded(limit, 200)
    files = _files(await _study(accession), accession)
    sdrf = next((f for f in files if f["path"].lower().endswith(".sdrf.txt")), None)
    if sdrf is None:
        raise ValueError(f"No SDRF sample annotation found for {accession}")
    response = await request("GET", sdrf["url"])
    reader = csv.reader(io.StringIO(response.text), delimiter="\t")
    columns = next(reader, [])
    if len(columns) < 2 or not any("source name" in c.lower() or "sample name" in c.lower() for c in columns):
        raise ValueError("Downloaded file is not an SDRF table")
    rows = list(islice(reader, limit + 1))
    return {"accession": accession, "columns": columns, "rows": rows[:limit],
            "truncated": len(rows) > limit, "source_url": sdrf["url"]}


TOOLS = (
    biostudies_search,
    biostudies_record,
    biostudies_files,
    biostudies_samples,
)


def resource_catalog() -> dict:
    """List valid collections, accessions formats and paging bounds."""
    return {"collections": ["arrayexpress", "all"],
            "accession_format": "E-{ARCHIVE}-{ID} or S-{TAG}{ID} (e.g. E-MTAB-1234)",
            "limit": "search 1-100, files/samples 1-200", "page": "1-1000",
            "offset": "0-100000 (files)"}


RESOURCES = (
    ("biostudies://collections", resource_catalog),
)
