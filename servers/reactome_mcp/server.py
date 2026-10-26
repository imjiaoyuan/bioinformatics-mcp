"""Reactome pathway content, reactions and participating molecules."""
from __future__ import annotations

from mcp.server.fastmcp import FastMCP

from common.api import choice, json_response, local_page
from common.http import bounded, identifier, text

mcp = FastMCP("reactome")
BASE = "https://reactome.org/ContentService"


def _id(value: str) -> str:
    return identifier(value.upper(), r"(?:R-[A-Z]{3}-[0-9]+(?:\.[0-9]+)?|[0-9]+)", "Reactome ID")


async def _list(path: str, limit: int, offset: int, params: dict | None = None) -> dict:
    bounded(limit)
    bounded(offset, 1_000_000, "offset", 0)
    data, source = await json_response(f"{BASE}/{path}", params)
    return local_page(data, limit, offset, **source)


@mcp.tool()
async def reactome_search(query: str, species: str = "Homo sapiens", limit: int = 20,
                          page: int = 1) -> dict:
    """Search pathways and reactions with upstream pagination (pages start at 1)."""
    params = {"query": text(query), "species": text(species, "species", 100),
              "types": ["Pathway", "Reaction"], "cluster": "false",
              "rowCount": bounded(limit), "page": bounded(page, 10000, "page")}
    data, source = await json_response(f"{BASE}/search/query/paginated", params)
    return {**source, "data": data, "limit": limit, "page": page}


@mcp.tool()
async def reactome_entry(reactome_id: str) -> dict:
    """Retrieve an event/entity record including available descriptions and references."""
    data, source = await json_response(f"{BASE}/data/query/{_id(reactome_id)}")
    return {**source, "data": data}


@mcp.tool()
async def reactome_pathway_events(reactome_id: str, limit: int = 20, offset: int = 0) -> dict:
    """List recursively contained events; paging is local over a byte-bounded upstream list."""
    return await _list(f"data/pathway/{_id(reactome_id)}/containedEvents", limit, offset)


@mcp.tool()
async def reactome_participants(reactome_id: str, limit: int = 20, offset: int = 0) -> dict:
    """List reference entities participating in an event, with local result pagination."""
    return await _list(f"data/participants/{_id(reactome_id)}/referenceEntities", limit, offset)


@mcp.tool()
async def reactome_pathways_for_gene(gene_id: str, resource: str = "UniProt",
                                     species: str = "Homo sapiens", limit: int = 20,
                                     offset: int = 0) -> dict:
    """Map a UniProt/Ensembl identifier to lower-level pathways; no ID conversion is implied."""
    choice(resource, {"UniProt", "Ensembl"}, "resource")
    return await _list(f"data/mapping/{resource}/{identifier(gene_id)}/pathways", limit, offset,
                       {"species": text(species, "species", 100)})


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
