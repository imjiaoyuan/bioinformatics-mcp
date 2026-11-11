"""Human Cell Atlas (Azul) and Broad Single Cell Portal study and sample metadata."""
from __future__ import annotations

import json

from common.api import choice, json_response
from common.http import bounded, identifier, text

AZUL = "https://service.azul.data.humancellatlas.org/index"
SCP = "https://singlecell.broadinstitute.org/single_cell/api/v1"


def _accession(value: str) -> str:
    return identifier(value.upper(), r"SCP[0-9]+", "Single Cell Portal accession")


def _uuid(value: str) -> str:
    return identifier(value.lower(), r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}",
                      "HCA project UUID")


async def hca_search(entity: str = "projects", field: str | None = None, value: str | None = None,
                     limit: int = 10, cursor: str | None = None) -> dict:
    """Search HCA Azul projects, samples or files; page with the returned cursor token.

    The Azul index has no free-text query: filter by providing a metadata field and
    exact value, for example field="organ", value="blood". termFacets are removed to
    bound the response.
    """
    choice(entity, {"projects", "samples", "files"}, "entity")
    params: dict = {"size": bounded(limit, 50)}
    if field is not None or value is not None:
        if field is None or value is None:
            raise ValueError("Provide both field and value to filter")
        filters = {text(field, "field", 100): {"is": [text(value, "value", 200)]}}
        params["filters"] = json.dumps(filters)
    if cursor is not None:
        params["search_after"] = text(cursor, "cursor", 1000)
    data, source = await json_response(f"{AZUL}/{entity}", params)
    data.pop("termFacets", None)
    data["pagination"]["model"] = "cursor"
    return {**source, **data}


async def hca_project(project_uuid: str) -> dict:
    """Retrieve one HCA project's contributors, publications, samples and file summaries."""
    data, source = await json_response(f"{AZUL}/projects/{_uuid(project_uuid)}")
    data.pop("termFacets", None)
    return {**source, **data}


async def scp_search_studies(query: str, page_number: int = 1) -> dict:
    """Search public Broad Single Cell Portal studies by keyword; returns matching accessions."""
    params = {"type": "study", "terms": text(query, 500), "page": bounded(page_number, 1000, "page_number", 1)}
    data, source = await json_response(f"{SCP}/search", params)
    return {**source, **data}


async def scp_study_annotations(accession: str) -> dict:
    """List cell annotations (names, types, values) available for one SCP study."""
    data, source = await json_response(f"{SCP}/studies/{_accession(accession)}/annotations")
    return {**source, "results": data}


async def scp_study_annotation(accession: str, annotation: str) -> dict:
    """Retrieve one named annotation, its scope and cell values, for one SCP study."""
    name = text(annotation, "annotation", 200)
    data, source = await json_response(f"{SCP}/studies/{_accession(accession)}/annotations/{name}")
    return {**source, **data}


async def scp_study_clusters(accession: str) -> dict:
    """List default and sub-cluster names available for one SCP study."""
    data, source = await json_response(f"{SCP}/studies/{_accession(accession)}/clusters")
    return {**source, "results": data}


async def scp_study_files_summary(accession: str) -> dict:
    """List downloadable file metadata for one SCP study via the public study view."""
    data, source = await json_response(f"{SCP}/site/studies/{_accession(accession)}")
    return {**source, **data}


TOOLS = (
    hca_search,
    hca_project,
    scp_search_studies,
    scp_study_annotations,
    scp_study_annotation,
    scp_study_clusters,
    scp_study_files_summary,
)


RESOURCES = ()
