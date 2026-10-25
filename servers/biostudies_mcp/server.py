"""BioStudies study search, associated files and ArrayExpress SDRF sample annotations."""
from __future__ import annotations

import csv
import io
from itertools import islice
from pathlib import PurePosixPath
from urllib.parse import quote, urlencode

from mcp.server.fastmcp import FastMCP

from common.http import bounded, get_json, identifier, request, text

mcp = FastMCP("biostudies")
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


@mcp.tool()
async def biostudies_search(query: str, collection: str = "arrayexpress", limit: int = 20, page: int = 1) -> dict:
    """Search ArrayExpress by default, or all public BioStudies using collection='all'."""
    if collection not in {"arrayexpress", "all"}:
        raise ValueError("collection must be arrayexpress or all")
    path = "search" if collection == "all" else "arrayexpress/search"
    params = {"query": text(query), "pageSize": bounded(limit), "page": bounded(page, 1000, "page")}
    data = await get_json(f"{BASE}/api/v1/{path}", params)
    return {**data, "source_url": f"{BASE}/api/v1/{path}?{urlencode(params)}"}


@mcp.tool()
async def biostudies_record(accession: str) -> dict:
    """Get the study tree, preserving study attributes, sections and external ENA links."""
    accession = _accession(accession)
    return {"study": await _study(accession), "source_url": f"{BASE}/studies/{accession}"}


@mcp.tool()
async def biostudies_files(accession: str, limit: int = 50, offset: int = 0) -> dict:
    """List files from nested study sections, including processed data and IDF/SDRF files."""
    accession = _accession(accession)
    bounded(limit, 200)
    bounded(offset, 100000, "offset", 0)
    files = _files(await _study(accession), accession)
    return {"files": files[offset:offset + limit], "total": len(files),
            "next_offset": offset + limit if offset + limit < len(files) else None,
            "source_url": f"{BASE}/studies/{accession}"}


@mcp.tool()
async def biostudies_samples(accession: str, limit: int = 20) -> dict:
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


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
