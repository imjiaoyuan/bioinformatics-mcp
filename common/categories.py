"""Curated provider categories with stable selection numbers.

Numbers have two parts: category and slot, e.g. ``1.3``. Slots are assigned
in the fixed order below so existing numbers keep their meaning when new
providers are added. Whole categories are selected with the bare category
number, e.g. ``2`` selects every protein/structure provider. Provider names
remain valid selections everywhere.
"""
from __future__ import annotations

import re

CATEGORIES: dict[int, tuple[str, tuple[str, ...]]] = {
    1: ("Sequence and genome annotation", (
        "ncbi", "ena", "ensembl", "sra", "cncb", "ucsc", "vep", "mygene",
        "hgnc", "taxonomy", "variation", "encode", "datasets", "rnacentral")),
    2: ("Protein and structure", (
        "uniprot", "pdb", "pdbe", "alphafold", "emdb", "interpro")),
    3: ("Pathways, networks and enrichment", (
        "kegg", "reactome", "string", "intact", "biogrid", "gprofiler",
        "msigdb", "quickgo", "bigg", "complexportal", "enrichr", "jaspar", "omnipath")),
    4: ("Expression and single cell", (
        "gtex", "hpa", "bgee", "panglao", "cellxgene", "singlecell",
        "expressionatlas")),
    5: ("Disease, clinical and drug", (
        "gdc", "cbioportal", "depmap", "civic", "clinvar", "disgenet",
        "mondo", "hpo", "pharmgkb", "opentargets", "gwas", "chembl",
        "pubchem", "clinicaltrials", "unichem", "rxnorm")),
    6: ("Archives, literature and terminology", (
        "biostudies", "publications", "mesh", "ols")),
    7: ("Model organisms and comparative genomics", (
        "alliance", "phytozome")),
    8: ("Metagenomics", ("metagenomics",)),
    9: ("Software and packages", (
        "bioconductor", "anaconda")),
}

_NUMBER = re.compile(r"^(\d+)(?:\.(\d+))?$")


def provider_numbers(commands: dict[str, str]) -> dict[str, str]:
    """Map every known provider name to its ``category.slot`` number."""
    numbers: dict[str, str] = {}
    for number, (_, providers) in CATEGORIES.items():
        for slot, provider in enumerate(providers, start=1):
            if provider in commands:
                numbers[provider] = f"{number}.{slot}"
    for provider in commands:
        numbers.setdefault(provider, "")
    return numbers


def resolve_selections(values: list[str], commands: dict[str, str]) -> list[str]:
    """Expand provider names, ``category.slot`` numbers and bare category
    numbers into a deduplicated provider list in selection order.

    Unknown values raise ValueError listing the valid forms. Selecting a
    bare category number expands to its installed providers in slot order.
    """
    numbers = provider_numbers(commands)
    by_number = {number: provider for provider, number in numbers.items() if number}
    selected: list[str] = []
    for value in values:
        name = value.strip().removesuffix("-mcp")
        if name in commands:
            if name not in selected:
                selected.append(name)
            continue
        match = _NUMBER.fullmatch(name)
        if match is None:
            raise ValueError(f"Unknown provider or number: {value}; run "
                             "'bioinformatics-mcp list' for numbered providers")
        category, slot = int(match[1]), match[2]
        if category not in CATEGORIES:
            raise ValueError(f"Unknown category number: {value}; valid 1-{max(CATEGORIES)}")
        if slot is None:
            for provider in CATEGORIES[category][1]:
                if provider in commands and provider not in selected:
                    selected.append(provider)
            continue
        provider = by_number.get(f"{category}.{int(slot)}")
        if provider is None:
            raise ValueError(f"Unknown provider number: {value}; run "
                             "'bioinformatics-mcp list' for numbered providers")
        if provider not in selected:
            selected.append(provider)
    if not selected:
        raise ValueError("No providers selected")
    return selected


def format_list(commands: dict[str, str]) -> str:
    """Numbered, category-grouped listing used by ``bioinformatics-mcp list``."""
    numbers = provider_numbers(commands)
    lines: list[str] = []
    for number, (label, providers) in CATEGORIES.items():
        installed = [provider for provider in providers if provider in commands]
        if not installed:
            continue
        lines.append(f"{number}. {label}")
        from common.cli import ENVIRONMENT_VARIABLES
        for slot, provider in enumerate(providers, start=1):
            if provider in commands:
                env = ENVIRONMENT_VARIABLES.get(provider)
                suffix = f"  [env: {', '.join(env)}]" if env else ""
                lines.append(f"   {number}.{slot} {provider}{suffix}")
    uncategorized = sorted(provider for provider, number in numbers.items()
                           if not number)
    if uncategorized:
        lines.append("?. Other installed providers")
        lines.extend(f"   ?   {provider}" for provider in uncategorized)
    return "\n".join(lines)
