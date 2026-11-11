"""DepMap portal datasets, cell lines, genes and drug sensitivity."""
from __future__ import annotations

from common.api import local_page
from common.http import identifier, text, get_json

API_BASE = "https://depmap.org/portal/api"
PORTAL_BASE = "https://depmap.org/portal"


def _model_id(value: str) -> str:
    return identifier(value.upper(), r"ACH-[0-9]{6}", "DepMap model ID (ACH-NNNNNN)")


def _label(value: str, name: str) -> str:
    return text(value, name, 150)


async def depmap_datasets(limit: int = 20, offset: int = 0) -> dict:
    """List matrix datasets available for custom download with local paging."""
    rows = await get_json(f"{API_BASE}/download/datasets")
    return local_page(rows, limit, offset, source_url=f"{API_BASE}/download/datasets")


async def depmap_cell_line_sensitivity(depmap_id: str) -> dict:
    """Retrieve priority-ranked compound sensitivity data for one cell line."""
    model_id = _model_id(depmap_id)
    data = await get_json(f"{PORTAL_BASE}/cell_line/compound_sensitivity/{model_id}")
    return {"source_url": f"{PORTAL_BASE}/cell_line/compound_sensitivity/{model_id}", **data}


async def depmap_cell_line_datasets(depmap_id: str) -> dict:
    """List datasets with available data for one cell line, grouped by data type."""
    model_id = _model_id(depmap_id)
    data = await get_json(f"{PORTAL_BASE}/cell_line/datasets/{model_id}")
    return {"source_url": f"{PORTAL_BASE}/cell_line/datasets/{model_id}", **data}


async def depmap_gene_characterization(gene_symbol: str) -> dict:
    """List biomarker dataset characterizations available for one gene symbol."""
    symbol = identifier(gene_symbol, r"[A-Za-z][A-Za-z0-9_.-]{0,48}", "gene symbol")
    url = f"{PORTAL_BASE}/gene/gene_characterization_data/{symbol}"
    rows = await get_json(url)
    return {"source_url": url, "results": rows}


async def depmap_compound_availability() -> dict:
    """List dose-response datasets and their metadata for compound sensitivity."""
    data = await get_json(f"{API_BASE}/compound/data_availability_metadata")
    return {"source_url": f"{API_BASE}/compound/data_availability_metadata", **data}


async def depmap_compound_drc_dataset(compound_label: str, compound_id: str) -> dict:
    """Retrieve the prioritized dose-response dataset options for one compound."""
    label = _label(compound_label, "compound_label")
    compound = text(compound_id, "compound_id", 150)
    params = {"compound_label": label, "compound_id": compound}
    data = await get_json(f"{API_BASE}/compound/prioritized_dataset", params)
    return {"source_url": f"{API_BASE}/compound/prioritized_dataset", **data}


async def depmap_compound_summary(compound_label: str, compound_id: str) -> dict:
    """Retrieve the consolidated compound page summary with dataset options and priorities."""
    label = _label(compound_label, "compound_label")
    compound = text(compound_id, "compound_id", 150)
    params = {"compound_label": label, "compound_id": compound}
    data = await get_json(f"{API_BASE}/compound/compound_summary", params)
    return {"source_url": f"{API_BASE}/compound/compound_summary", **data}


async def depmap_compound_dose_curves(compound_id: str, drc_dataset_label: str,
                                      replicate_dataset_name: str) -> dict:
    """Retrieve fitted dose-response curve parameters per cell line for one compound.

    Curve fit values (EC50, AUC, slopes and asymptotes) are reported as fitted;
    no refitting or conversion across datasets is performed.
    """
    params = {
        "compound_id": text(compound_id, "compound_id", 150),
        "drc_dataset_label": _label(drc_dataset_label, "drc_dataset_label"),
        "replicate_dataset_name": _label(replicate_dataset_name, "replicate_dataset_name"),
    }
    data = await get_json(f"{API_BASE}/compound/dose_curve_data", params)
    return {"source_url": f"{API_BASE}/compound/dose_curve_data", **data}


TOOLS = (
    depmap_datasets,
    depmap_cell_line_sensitivity,
    depmap_cell_line_datasets,
    depmap_gene_characterization,
    depmap_compound_availability,
    depmap_compound_drc_dataset,
    depmap_compound_summary,
    depmap_compound_dose_curves,
)


RESOURCES = ()
