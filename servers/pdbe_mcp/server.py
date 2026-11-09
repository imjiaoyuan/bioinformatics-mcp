"""PDBe entry summaries, SIFTS mappings, PDBe-KB aggregates and ligand/residue data."""
from __future__ import annotations

from mcp.server.fastmcp import FastMCP

from common.api import json_response
from common.http import identifier

mcp = FastMCP("pdbe")
BASE = "https://www.ebi.ac.uk/pdbe/api"


def _entry_id(value: str) -> str:
    return identifier(value.lower(), r"[0-9][A-Za-z0-9]{3}", "PDB entry ID")


async def _get(path: str) -> dict:
    data, source = await json_response(f"{BASE}/{path}/")
    return {**source, **data}


@mcp.tool()
async def pdbe_entry_summary(entry_id: str) -> dict:
    """Retrieve an entry's title, experimental method, dates, entities and assemblies."""
    return await _get(f"pdb/entry/summary/{_entry_id(entry_id)}")


@mcp.tool()
async def pdbe_sifts_uniprot(entry_id: str) -> dict:
    """Retrieve SIFTS UniProt-to-sequence mappings with residue ranges and coverage.

    Entries without any UniProt mapping return upstream HTTP 404.
    """
    return await _get(f"mappings/uniprot/{_entry_id(entry_id)}")


@mcp.tool()
async def pdbe_sifts_ena(entry_id: str) -> dict:
    """Retrieve SIFTS ENA (nucleotide sequence database) mappings for an entry.

    Entries without any ENA mapping return upstream HTTP 404.
    """
    return await _get(f"mappings/ena/{_entry_id(entry_id)}")


@mcp.tool()
async def pdbe_pdbe_kb_summary(entry_id: str) -> dict:
    """Retrieve PDBe-KB aggregated mappings (UniProt, Pfam, ENA and more) for an entry."""
    return await _get(f"mappings/all/{_entry_id(entry_id)}")


@mcp.tool()
async def pdbe_ligands(entry_id: str) -> dict:
    """Retrieve ligand monomers with chain, residue numbers, names and molecular weights."""
    return await _get(f"pdb/entry/ligand_monomers/{_entry_id(entry_id)}")


@mcp.tool()
async def pdbe_modified_residues(entry_id: str) -> dict:
    """Retrieve modified amino acids or nucleotides and their parent components.

    Entries without modified residues return upstream HTTP 404.
    """
    return await _get(f"pdb/entry/modified_residues_or_NA/{_entry_id(entry_id)}")


@mcp.tool()
async def pdbe_secondary_structure(entry_id: str) -> dict:
    """Retrieve per-chain helices and strands with residue ranges."""
    return await _get(f"pdb/entry/secondary_structure/{_entry_id(entry_id)}")


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
