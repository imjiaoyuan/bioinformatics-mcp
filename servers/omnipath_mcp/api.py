"""OmniPath human signaling networks: interactions, enzyme-PTM, complexes and annotations.

Queries the public OmniPath web API (https://omnipathdb.org, Saez Lab). Interactions
aggregate dozens of resources (CollecTRI, OmniPath core, TF targets); respect the
resource licences listed in the `sources` field when redistributing.
"""
from __future__ import annotations

from typing import Annotated

from pydantic import Field

from common.api import json_response, local_page, page
from common.http import bounded, identifiers, text

BASE = "https://omnipathdb.org"


def _partners(values: list[str], name: str = "identifiers") -> str:
    return ",".join(identifiers(values, 10))


async def omnipath_interactions(proteins: list[str],
                                organisms: Annotated[int, Field(ge=1, le=100_000)] = 9606,
                                limit: Annotated[int, Field(ge=1, le=100)] = 20,
                                offset: Annotated[int, Field(ge=0, le=1_000_000)] = 0) -> dict:
    """Retrieve signaling interactions (directed, signed) that involve the given proteins.

    ``proteins`` are UniProt accessions or gene symbols (1-10). Rows carry direction,
    stimulation/inhibition consensus, upstream sources and references.
    """
    paging = page(limit, offset)
    data, source = await json_response(f"{BASE}/interactions/", {
        "format": "json", "organisms": bounded(organisms, 100_000, "organisms"), "partners": _partners(proteins),
        "genesymbols": "yes", "fields": "sources,references,type"})
    return {**source, **local_page(data, paging["limit"], paging["offset"])}


async def omnipath_enzyme_substrate(enzyme: str | None = None, substrate: str | None = None,
                                    limit: Annotated[int, Field(ge=1, le=100)] = 20,
                                    offset: Annotated[int, Field(ge=0, le=1_000_000)] = 0) -> dict:
    """Retrieve enzyme-substrate post-translational modification sites (phosphorylation etc.).

    Provide at least one of ``enzyme`` / ``substrate`` (UniProt accession or gene symbol).
    """
    if enzyme is None and substrate is None:
        raise ValueError("Provide at least one of enzyme or substrate")
    params: dict = {"format": "json"}
    if enzyme is not None:
        params["enzymes"] = _partners([enzyme])
    if substrate is not None:
        params["substrates"] = _partners([substrate])
    paging = page(limit, offset)
    data, source = await json_response(f"{BASE}/enz_sub/", params)
    return {**source, **local_page(data, paging["limit"], paging["offset"])}


async def omnipath_complexes(proteins: list[str],
                             limit: Annotated[int, Field(ge=1, le=100)] = 20,
                             offset: Annotated[int, Field(ge=0, le=1_000_000)] = 0) -> dict:
    """Retrieve protein complexes that contain any of the given proteins, with stoichiometry."""
    paging = page(limit, offset)
    data, source = await json_response(f"{BASE}/complexes/", {
        "format": "json", "proteins": _partners(proteins)})
    return {**source, **local_page(data, paging["limit"], paging["offset"])}


async def omnipath_annotations(proteins: list[str],
                               limit: Annotated[int, Field(ge=1, le=100)] = 20,
                               offset: Annotated[int, Field(ge=0, le=1_000_000)] = 0) -> dict:
    """Retrieve category-labelled annotations (e.g. tf_type, SignaLink roles) for proteins."""
    paging = page(limit, offset)
    data, source = await json_response(f"{BASE}/annotations/", {
        "format": "json", "proteins": _partners(proteins)})
    return {**source, **local_page(data, paging["limit"], paging["offset"])}


TOOLS = (
    omnipath_interactions,
    omnipath_enzyme_substrate,
    omnipath_complexes,
    omnipath_annotations,
)
