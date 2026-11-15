"""PDBe entry summaries, SIFTS mappings, PDBe-KB aggregates and ligand/residue data."""
from __future__ import annotations

import json

from common.api import json_response
from common.http import identifier

BASE = "https://www.ebi.ac.uk/pdbe/api"


def _entry_id(value: str) -> str:
    return identifier(value.lower(), r"[0-9][A-Za-z0-9]{3}", "PDB entry ID")


async def _get(path: str) -> dict:
    data, source = await json_response(f"{BASE}/{path}/")
    return {**source, **data}


async def pdbe_entry_summary(entry_id: str) -> dict:
    """Retrieve an entry's title, experimental method, dates, entities and assemblies."""
    return await _get(f"pdb/entry/summary/{_entry_id(entry_id)}")


async def pdbe_sifts_uniprot(entry_id: str) -> dict:
    """Retrieve SIFTS UniProt-to-sequence mappings with residue ranges and coverage.

    Entries without any UniProt mapping return upstream HTTP 404.
    """
    return await _get(f"mappings/uniprot/{_entry_id(entry_id)}")


async def pdbe_sifts_ena(entry_id: str) -> dict:
    """Retrieve SIFTS ENA (nucleotide sequence database) mappings for an entry.

    Entries without any ENA mapping return upstream HTTP 404.
    """
    return await _get(f"mappings/ena/{_entry_id(entry_id)}")


async def pdbe_pdbe_kb_summary(entry_id: str) -> dict:
    """Retrieve PDBe-KB aggregated mappings (UniProt, Pfam, ENA and more) for an entry."""
    return await _get(f"mappings/all/{_entry_id(entry_id)}")


async def pdbe_ligands(entry_id: str) -> dict:
    """Retrieve ligand monomers with chain, residue numbers, names and molecular weights."""
    return await _get(f"pdb/entry/ligand_monomers/{_entry_id(entry_id)}")


async def pdbe_modified_residues(entry_id: str) -> dict:
    """Retrieve modified amino acids or nucleotides and their parent components.

    Entries without modified residues return upstream HTTP 404.
    """
    return await _get(f"pdb/entry/modified_residues_or_NA/{_entry_id(entry_id)}")


async def pdbe_secondary_structure(entry_id: str) -> dict:
    """Retrieve per-chain helices and strands with residue ranges."""
    return await _get(f"pdb/entry/secondary_structure/{_entry_id(entry_id)}")


TOOLS = (
    pdbe_entry_summary,
    pdbe_sifts_uniprot,
    pdbe_sifts_ena,
    pdbe_pdbe_kb_summary,
    pdbe_ligands,
    pdbe_modified_residues,
    pdbe_secondary_structure,
)


def endpoints() -> str:
    """Describe the PDBe REST endpoints and entry-ID constraint used by this server."""
    return json.dumps({
        "resource": "pdbe://endpoints",
        "base": BASE,
        "entry_id_pattern": "[0-9][A-Za-z0-9]{3}",
        "endpoints": {
            "pdbe_entry_summary": "pdb/entry/summary/{entry_id}",
            "pdbe_sifts_uniprot": "mappings/uniprot/{entry_id}",
            "pdbe_sifts_ena": "mappings/ena/{entry_id}",
            "pdbe_pdbe_kb_summary": "mappings/all/{entry_id}",
            "pdbe_ligands": "pdb/entry/ligand_monomers/{entry_id}",
            "pdbe_modified_residues": "pdb/entry/modified_residues_or_NA/{entry_id}",
            "pdbe_secondary_structure": "pdb/entry/secondary_structure/{entry_id}",
        },
        "notes": "Entries without the requested mapping return upstream HTTP 404.",
    })


RESOURCES = (
    ("pdbe://endpoints", endpoints),
)
