"""MetaboLights metabolomics studies: catalogue, metadata, files and assays.

Queries the public MetaboLights web service (https://www.ebi.ac.uk/metabolights/ws).
Check each study's datasetLicense field before redistribution; MetaboLights
content terms vary per submission.
"""
from __future__ import annotations

from typing import Annotated

from pydantic import Field

from common.api import json_response, local_page, page
from common.http import bounded, identifier

BASE = "https://www.ebi.ac.uk/metabolights/ws"

_STUDY_KEYS = ("mhdAccession", "studyStatus", "datasetLicense", "datasetLicenseUrl",
                "firstPublicDate", "studyFtpUrl", "studyHttpUrl", "studyGlobusUrl",
                "studyCategory", "sampleTemplate", "revisionNumber", "revisionDatetime",
                "curationRequest")


def _accession(value: str) -> str:
    return identifier(value.upper(), r"MTBLS[0-9]+", "MetaboLights accession")


async def metabolights_studies(limit: Annotated[int, Field(ge=1, le=100)] = 20,
                               offset: Annotated[int, Field(ge=0, le=100_000)] = 0) -> dict:
    """List all public MetaboLights study accessions (sliced locally from the catalogue)."""
    page(limit, offset)
    data, source = await json_response(f"{BASE}/studies")
    rows = data.get("content", [])
    return {**source, **local_page(rows, limit, offset)}


async def metabolights_study(accession: str) -> dict:
    """Retrieve one study's metadata: status, licence, release date and download URLs.

    Submitter contact details are deliberately excluded.
    """
    data, source = await json_response(f"{BASE}/studies/{_accession(accession)}")
    study = data.get("mtblsStudy")
    if not isinstance(study, dict):
        raise ValueError(f"No MetaboLights study matches {_accession(accession)}")
    return {**source, **{key: study[key] for key in _STUDY_KEYS if key in study}}


async def metabolights_study_files(accession: str,
                                   limit: Annotated[int, Field(ge=1, le=100)] = 50,
                                   offset: Annotated[int, Field(ge=0, le=100_000)] = 0) -> dict:
    """List the files attached to one study with their directory, size and checksums."""
    accession = _accession(accession)
    paging = page(limit, offset)
    data, source = await json_response(f"{BASE}/studies/{accession}/files")
    rows = data.get("study", []) if isinstance(data, dict) else []
    return {**source, **local_page(rows, paging["limit"], paging["offset"]), "accession": accession}


async def metabolights_study_assays(accession: str) -> dict:
    """List assay filenames (one per assay technology) attached to one study."""
    data, source = await json_response(f"{BASE}/studies/{_accession(accession)}/assays")
    assays = data.get("data", {}).get("assays", [])
    return {**source, "accession": _accession(accession), "assays": assays, "total": len(assays)}


TOOLS = (
    metabolights_studies,
    metabolights_study,
    metabolights_study_files,
    metabolights_study_assays,
)
