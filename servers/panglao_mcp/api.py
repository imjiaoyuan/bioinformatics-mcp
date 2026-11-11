"""PanglaoDB cell-type marker genes.

Upstream caveat: PanglaoDB exposes no structured JSON API. The only stable
public machine-readable endpoint announced by the maintainers (see the
PanglaoDB news section) is the dated marker snapshot in tab-separated,
gzip-compressed form. It is fetched in memory, decompressed, and sliced
locally; values therefore reflect that snapshot (2020-03-27) and are not a
live database view. No HTML scraping and no files are written to disk.
"""
from __future__ import annotations

import csv
import gzip
import io
from typing import Any

from common.api import choice, local_page
from common.http import identifier, request, text

BASE = "https://panglaodb.se"
MARKERS_URL = f"{BASE}/markers/PanglaoDB_markers_27_Mar_2020.tsv.gz"

_COLUMNS = {
    "species": "species",
    "official gene symbol": "gene",
    "cell type": "cell_type",
    "nicknames": "nicknames",
    "ubiquitousness index": "ubiquitousness_index",
    "product description": "product_description",
    "gene type": "gene_type",
    "canonical marker": "canonical_marker",
    "germ layer": "germ_layer",
    "organ": "organ",
    "sensitivity_human": "sensitivity_human",
    "sensitivity_mouse": "sensitivity_mouse",
    "specificity_human": "specificity_human",
    "specificity_mouse": "specificity_mouse",
}


async def _rows() -> list[dict[str, Any]]:
    response = await request("GET", MARKERS_URL)
    raw = gzip.decompress(response.content)
    rows: list[dict[str, Any]] = []
    for record in csv.DictReader(io.StringIO(raw.decode("utf-8")), delimiter="\t"):
        rows.append({_COLUMNS[key]: value for key, value in record.items() if key in _COLUMNS})
    return rows


def _species_filter(value: str) -> set[str]:
    """Map a species choice to the upstream species column codes it covers."""
    return {"both": {"Mm", "Hs"}, "mouse": {"Mm"}, "human": {"Hs"}}[
        choice(value, {"both", "mouse", "human"}, "species")]


def _matches_species(row: dict[str, Any], codes: set[str]) -> bool:
    return any(code in row["species"].split() for code in codes)


async def panglao_cell_types(species: str = "both", limit: int = 20, offset: int = 0) -> dict:
    """List distinct PanglaoDB cell types with their organ and marker-gene counts.

    Results reflect the static marker snapshot (2020-03-27), not a live view.
    """
    counts: dict[tuple[str, str], int] = {}
    codes = _species_filter(species)
    for row in await _rows():
        if _matches_species(row, codes):
            key = (row["cell_type"], row["organ"])
            counts[key] = counts.get(key, 0) + 1
    listing = [{"cell_type": cell_type, "organ": organ, "marker_count": count}
               for (cell_type, organ), count in sorted(counts.items())]
    return local_page(listing, limit, offset, source_url=MARKERS_URL, species=species)


async def panglao_cell_type_markers(cell_type: str, species: str = "both",
                                    limit: int = 20, offset: int = 0) -> dict:
    """Retrieve the marker genes recorded for one cell type (case-insensitive name).

    Includes ubiquitousness index, sensitivity and specificity per species, all
    from the static marker snapshot (2020-03-27).
    """
    name = text(cell_type, "cell_type", 150).lower()
    codes = _species_filter(species)
    matched = [row for row in await _rows()
               if row["cell_type"].lower() == name and _matches_species(row, codes)]
    if not matched:
        raise ValueError(f"Unknown cell type in the PanglaoDB snapshot: {cell_type}")
    return local_page(matched, limit, offset, source_url=MARKERS_URL, cell_type=cell_type,
                      total_snapshot_rows=len(matched))


async def panglao_gene_markers(gene: str) -> dict:
    """Retrieve every cell type for which one official gene symbol is a marker.

    Gene symbols are matched case-insensitively against the static snapshot
    (2020-03-27).
    """
    symbol = identifier(gene.upper(), r"[A-Za-z0-9@.-]+", "gene symbol")
    matched = [row for row in await _rows() if row["gene"].upper() == symbol]
    return {"source_url": MARKERS_URL, "gene": symbol, "results": matched,
            "total": len(matched)}


async def panglao_markers_by_organ(organ: str, canonical_only: bool = False,
                                   species: str = "both", limit: int = 20,
                                   offset: int = 0) -> dict:
    """List marker genes for one organ, optionally restricted to canonical markers.

    Organ names are matched case-insensitively; data come from the static
    marker snapshot (2020-03-27).
    """
    name = text(organ, "organ", 150).lower()
    codes = _species_filter(species)
    matched = [row for row in await _rows()
               if row["organ"].lower() == name and _matches_species(row, codes)
               and (not canonical_only or row["canonical_marker"] == "1")]
    if not matched:
        raise ValueError(f"Unknown organ in the PanglaoDB snapshot: {organ}")
    return local_page(matched, limit, offset, source_url=MARKERS_URL, organ=organ,
                      canonical_only=canonical_only)


async def panglao_search_markers(query: str, species: str = "both",
                                 limit: int = 20, offset: int = 0) -> dict:
    """Substring-search marker rows by gene symbol, nicknames or product description.

    Matching is case-insensitive and bounded locally; data come from the static
    marker snapshot (2020-03-27).
    """
    needle = text(query, "query", 150).lower()
    codes = _species_filter(species)
    matched = []
    for row in await _rows():
        if not _matches_species(row, codes):
            continue
        haystack = " ".join([row["gene"], row["nicknames"], row["product_description"]]).lower()
        if needle in haystack:
            matched.append(row)
    return local_page(matched, limit, offset, source_url=MARKERS_URL, query=query)


TOOLS = (
    panglao_cell_types,
    panglao_cell_type_markers,
    panglao_gene_markers,
    panglao_markers_by_organ,
    panglao_search_markers,
)


RESOURCES = ()
