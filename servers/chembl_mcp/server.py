"""ChEMBL compounds, targets, assays and measured bioactivities."""
from __future__ import annotations

from mcp.server.fastmcp import FastMCP

from common.api import choice, json_response, page
from common.http import identifier, text

mcp = FastMCP("chembl")
BASE = "https://www.ebi.ac.uk/chembl/api/data"


def _id(value: str) -> str:
    return identifier(value.upper(), r"CHEMBL[0-9]+", "ChEMBL ID")


async def _get(path: str, params: dict | None = None) -> dict:
    data, source = await json_response(f"{BASE}/{path}.json", params)
    return {**source, **data}


@mcp.tool()
async def chembl_search(query: str, resource: str = "molecule", limit: int = 20,
                        offset: int = 0) -> dict:
    """Search compounds, targets or assays; preserve upstream pagination metadata."""
    choice(resource, {"molecule", "target", "assay"}, "resource")
    return await _get(f"{resource}/search", {**page(limit, offset), "q": text(query)})


@mcp.tool()
async def chembl_molecule(chembl_id: str) -> dict:
    """Retrieve a compound's structures, properties and hierarchy."""
    return await _get(f"molecule/{_id(chembl_id)}")


@mcp.tool()
async def chembl_target(chembl_id: str) -> dict:
    """Retrieve a target and its component proteins and organism."""
    return await _get(f"target/{_id(chembl_id)}")


@mcp.tool()
async def chembl_activities(target_id: str | None = None, molecule_id: str | None = None,
                            standard_type: str | None = None, limit: int = 20,
                            offset: int = 0) -> dict:
    """Retrieve measured activities, preserving units, relation, assay and validity flags.

    IC50, Ki and other measurements are not automatically converted or pooled.
    """
    params = page(limit, offset)
    if target_id is None and molecule_id is None:
        raise ValueError("Provide target_id or molecule_id")
    for key, value in {"target_chembl_id": target_id, "molecule_chembl_id": molecule_id}.items():
        if value is not None:
            params[key] = _id(value)
    if standard_type is not None:
        params["standard_type"] = text(standard_type, "standard_type", 100)
    return await _get("activity", params)


@mcp.tool()
async def chembl_assay(chembl_id: str) -> dict:
    """Retrieve assay description, confidence, target and source document identifiers."""
    return await _get(f"assay/{_id(chembl_id)}")


@mcp.tool()
async def chembl_mechanisms(molecule_id: str, limit: int = 20, offset: int = 0) -> dict:
    """Retrieve curated mechanisms of action for one compound."""
    return await _get("mechanism", {**page(limit, offset), "molecule_chembl_id": _id(molecule_id)})


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
