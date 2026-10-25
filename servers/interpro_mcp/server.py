"""InterPro family/domain/site records, GO mappings and protein matches."""
from __future__ import annotations

import httpx
from mcp.server.fastmcp import FastMCP

from common.http import bounded, identifier, request, text

mcp = FastMCP("interpro")
BASE = "https://www.ebi.ac.uk/interpro/api"


def _database(value: str) -> str:
    if value not in {"interpro", "pfam"}:
        raise ValueError("database must be interpro or pfam")
    return value


def _entry(value: str) -> tuple[str, str]:
    value = identifier(value.upper(), r"(?:IPR[0-9]{6}|PF[0-9]{5})", "InterPro/Pfam accession")
    return ("interpro" if value.startswith("IPR") else "pfam"), value


def _page(limit: int, cursor: str | None) -> dict:
    params = {"page_size": bounded(limit, 200)}
    if cursor is not None:
        params["cursor"] = text(cursor, "cursor", 2000)
    return params


async def _api(path: str, params: dict | None = None) -> dict:
    url = f"{BASE}/{path.strip('/')}/"
    try:
        response = await request("GET", url, params=params)
    except httpx.HTTPStatusError as exc:
        if exc.response.status_code == 408:
            return {"status": "pending", "message": "InterPro is computing this query; retry later",
                    "source_url": str(exc.request.url)}
        raise
    data = {"count": 0, "results": [], "next": None} if response.status_code == 204 else response.json()
    return {**data, "status": "ok", "source_url": str(response.url)}


@mcp.tool()
async def interpro_search(query: str, database: str = "interpro", limit: int = 20,
                          cursor: str | None = None) -> dict:
    """Search InterPro or Pfam family/domain/site entries, preserving API pagination."""
    params = {**_page(limit, cursor), "search": text(query)}
    return await _api(f"entry/{_database(database)}", params)


@mcp.tool()
async def interpro_entry(accession: str) -> dict:
    """Retrieve a detailed IPR/PF entry including available descriptions and GO annotations."""
    database, accession = _entry(accession)
    return await _api(f"entry/{database}/{accession}")


@mcp.tool()
async def interpro_protein_annotations(accession: str, database: str = "interpro",
                                       limit: int = 20, cursor: str | None = None) -> dict:
    """Get existing family/domain/site matches and their locations on a UniProt protein."""
    accession = identifier(accession.upper(), r"[A-Z0-9]{6,10}(?:-[0-9]+)?", "UniProt accession")
    return await _api(f"entry/{_database(database)}/protein/uniprot/{accession}", _page(limit, cursor))


@mcp.tool()
async def interpro_proteins(accession: str, taxon_id: int | None = None,
                            reviewed_only: bool = True, limit: int = 20, cursor: str | None = None) -> dict:
    """List proteins matching a domain/family, optionally restricted to a taxon."""
    database, accession = _entry(accession)
    path = f"protein/{'reviewed' if reviewed_only else 'uniprot'}/entry/{database}/{accession}"
    if taxon_id is not None:
        path += f"/taxonomy/uniprot/{bounded(taxon_id, 10_000_000, 'taxon_id')}"
    return await _api(path, _page(limit, cursor))


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
