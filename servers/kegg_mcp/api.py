"""KEGG pathways, genes and compounds via the KEGG REST API.

Selecting the KEGG provider does not grant rights to KEGG data; KEGG content
remains subject to the KEGG license terms and must not be redistributed.
"""
from __future__ import annotations

import re

from common.api import choice, local_page
from common.http import identifier, request, text

BASE = "https://rest.kegg.jp"

DATABASES = {
    "pathway", "module", "ko", "genes", "genome", "compound", "glycan",
    "reaction", "rclass", "enzyme", "network", "disease", "drug", "dgroup",
}
GET_OPTIONS = {"aaseq", "ntseq", "mol", "kcf", "conf", "kgml", "json"}
FIND_OPTIONS = {"formula", "exact_mass", "mol_weight", "nop"}
ORGANISM = re.compile(r"[a-z]{3,4}|T[0-9]{5}")


def _db(database: str) -> str:
    return choice(database, DATABASES, "database")


def _organism(organism: str | None) -> str | None:
    if organism is None:
        return None
    value = identifier(organism.lower(), r"[a-z0-9]+", "organism code")
    if not ORGANISM.fullmatch(value):
        raise ValueError("Invalid organism code")
    return value


def _entries(values: list[str], maximum: int = 10) -> str:
    if not values or len(values) > maximum:
        raise ValueError(f"entries must contain 1-{maximum} items")
    return "+".join(
        identifier(value, r"[A-Za-z0-9]+:[A-Za-z0-9_.-]+|[A-Za-z]+[0-9]{5}", "KEGG entry ID")
        for value in values
    )


def _parse_table(body: str) -> list[dict]:
    rows = []
    for line in body.splitlines():
        if not line.strip():
            continue
        fields = line.split("\t", 1)
        rows.append({"id": fields[0], "description": fields[1] if len(fields) > 1 else ""})
    return rows


async def _get_text(path: str) -> tuple[str, dict]:
    response = await request("GET", f"{BASE}/{path}", interval=1.0)
    return response.text, {"source_url": str(response.url)}


async def kegg_list(database: str, organism: str | None = None, limit: int = 20,
                    offset: int = 0) -> dict:
    """List entry identifiers and names for a KEGG database, optionally per organism.

    Locally slices the byte-bounded upstream list; results carry local pagination.
    """
    database = _db(database)
    organism = _organism(organism) if organism is not None else None
    body, source = await _get_text(f"list/{database}" + (f"/{organism}" if organism else ""))
    return local_page(_parse_table(body), limit, offset, **source)


async def kegg_find(database: str, query: str, option: str | None = None,
                    limit: int = 20, offset: int = 0) -> dict:
    """Find KEGG entries matching a keyword, or a formula/mass/molecular-weight query.

    Options formula, exact_mass, mol_weight and nop apply only to compound and drug.
    """
    database = _db(database)
    query = text(query, "query", 200)
    if option is not None:
        choice(option, FIND_OPTIONS, "option")
        if database not in {"compound", "drug"}:
            raise ValueError("option requires database compound or drug")
    body, source = await _get_text(f"find/{database}/{query}" + (f"/{option}" if option else ""))
    return local_page(_parse_table(body), limit, offset, **source)


async def kegg_get(entry_ids: list[str], option: str | None = None) -> dict:
    """Retrieve up to 10 KEGG entries in flat file format, with an optional field view.

    Options: aaseq, ntseq, mol, kcf, conf, kgml, json; kgml and json take one pathway
    or brite entry respectively. Binary image data is intentionally not supported.
    """
    entries = _entries(entry_ids)
    body, source = await _get_text(
        f"get/{entries}" + (f"/{choice(option, GET_OPTIONS, 'option')}" if option else "")
    )
    return {**source, "entry_ids": entries, "text": body[:100_000]}


async def kegg_link(target_db: str, entry_ids: list[str], limit: int = 20,
                    offset: int = 0) -> dict:
    """Find entries in target_db cross-referenced by up to 10 KEGG entries.

    Returns tabular cross-references, for example pathways linked from genes.
    """
    choice(target_db, DATABASES, "target_db")
    entries = _entries(entry_ids)
    body, source = await _get_text(f"link/{target_db}/{entries}")
    return local_page(_parse_table(body), limit, offset, **source)


async def kegg_conv(target_db: str, entry_ids: list[str], limit: int = 20,
                    offset: int = 0) -> dict:
    """Convert up to 10 KEGG identifiers to or from outside identifiers.

    Target must be an organism code, ncbi-geneid, ncbi-proteinid or uniprot for genes,
    or pubchem or chebi for compounds, glycans and drugs.
    """
    if target_db not in DATABASES | {"ncbi-geneid", "ncbi-proteinid", "uniprot", "pubchem", "chebi"}:
        raise ValueError("target_db must be a KEGG database or supported outside database")
    entries = _entries(entry_ids)
    body, source = await _get_text(f"conv/{identifier(target_db, r'[a-z-]+', 'target_db')}/{entries}")
    return local_page(_parse_table(body), limit, offset, **source)


TOOLS = (
    kegg_list,
    kegg_find,
    kegg_get,
    kegg_link,
    kegg_conv,
)


RESOURCES = ()
