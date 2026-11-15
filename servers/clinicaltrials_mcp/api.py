"""Bounded ClinicalTrials.gov API v2 queries (https://clinicaltrials.gov/api/v2)."""
from __future__ import annotations

from typing import Annotated, Any, Literal

from pydantic import Field

from common.api import choice
from common.http import bounded, get_json, identifier, text

BASE = "https://clinicaltrials.gov/api/v2"
STATUSES = {"recruiting", "active_not_recruiting", "not_yet_recruiting", "completed",
            "enrolling_by_invitation", "suspended", "terminated", "withdrawn", "unknown"}


def _nct(value: str) -> str:
    return identifier(value.upper(), r"NCT[0-9]{8}", "NCT identifier")


def _criteria(query: str | None, param: str) -> str | None:
    return text(query, param) if query is not None else None


def _search_params(condition: str | None, intervention: str | None, title: str | None,
                   term: str | None, status: str | None, limit: int, cursor: str | None) -> dict:
    if all(value is None for value in (condition, intervention, title, term)):
        raise ValueError("Provide at least one of condition, intervention, title or term")
    params: dict[str, Any] = {"pageSize": bounded(limit, 100)}
    if condition is not None:
        params["query.cond"] = _criteria(condition, "condition")
    if intervention is not None:
        params["query.intr"] = _criteria(intervention, "intervention")
    if title is not None:
        params["query.titles"] = _criteria(title, "title")
    if term is not None:
        params["query.term"] = _criteria(term, "term")
    if status is not None:
        params["filter.overallStatus"] = choice(status.upper(), {s.upper() for s in STATUSES}, "status")
    if cursor is not None:
        params["pageToken"] = text(cursor, "cursor", 500)
    return params


def _summary(study: dict) -> dict:
    protocol = study.get("protocolSection", {})
    identification = protocol.get("identificationModule", {})
    status = protocol.get("statusModule", {})
    sponsor = protocol.get("sponsorCollaboratorsModule", {})
    design = protocol.get("designModule", {})
    nct_id = identification.get("nctId", "")
    return {
        "nct_id": nct_id,
        "brief_title": identification.get("briefTitle"),
        "overall_status": status.get("overallStatus"),
        "phases": design.get("phases", []),
        "enrollment": design.get("enrollmentInfo", {}).get("count"),
        "lead_sponsor": sponsor.get("leadSponsor", {}).get("name"),
        "source_url": f"https://clinicaltrials.gov/study/{nct_id}" if nct_id else None,
    }


async def trial_search(condition: str | None = None, intervention: str | None = None,
                       title: str | None = None, term: str | None = None,
                       status: Literal["recruiting", "active_not_recruiting", "not_yet_recruiting",
                                       "completed", "enrolling_by_invitation", "suspended",
                                       "terminated", "withdrawn", "unknown"] | None = None,
                       limit: Annotated[int, Field(ge=1, le=100)] = 10,
                       cursor: str | None = None) -> dict:
    """Search ClinicalTrials.gov studies; return matches and a cursor for the next page.

    Upstream uses opaque cursor pagination (no offsets): pass the returned
    ``next_cursor`` back as ``cursor`` to fetch subsequent pages. Bounds are
    validated before any request; results are capped at 100 per page.
    """
    params = _search_params(condition, intervention, title, term, status, limit, cursor)
    result = await get_json(f"{BASE}/studies", params=params)
    return {
        "studies": [_summary(study) for study in result.get("studies", [])],
        "next_cursor": result.get("nextPageToken"),
        "has_more": result.get("nextPageToken") is not None,
        "pagination": "cursor",
        "source_url": f"{BASE}/studies",
    }


async def trial_study(nct_id: str) -> dict:
    """Retrieve one ClinicalTrials.gov study: identification, status, sponsor, design, arms, eligibility, outcomes and results."""
    nct = _nct(nct_id)
    result = await get_json(f"{BASE}/studies/{nct}")
    protocol = result.get("protocolSection", {})
    identification = protocol.get("identificationModule", {})
    status = protocol.get("statusModule", {})
    sponsor = protocol.get("sponsorCollaboratorsModule", {})
    design = protocol.get("designModule", {})
    arms = protocol.get("armsInterventionsModule", {})
    eligibility = protocol.get("eligibilityModule", {})
    outcomes = protocol.get("outcomesModule", {})
    has_results = "resultsSection" in result
    return {
        "nct_id": identification.get("nctId", nct),
        "brief_title": identification.get("briefTitle"),
        "official_title": identification.get("officialTitle"),
        "organization": identification.get("organization", {}).get("fullName"),
        "overall_status": status.get("overallStatus"),
        "last_known_status": status.get("lastKnownStatus"),
        "why_stopped": status.get("whyStopped"),
        "lead_sponsor": sponsor.get("leadSponsor", {}).get("name"),
        "collaborators": [c.get("name") for c in sponsor.get("collaborators", [])],
        "study_type": design.get("studyInfo", {}).get("studyType"),
        "phases": design.get("phases", []),
        "enrollment": design.get("enrollmentInfo", {}).get("count"),
        "allocation": design.get("studyInfo", {}).get("allocation"),
        "primary_purpose": design.get("studyInfo", {}).get("primaryPurpose"),
        "masking": design.get("studyInfo", {}).get("maskingInfo", {}).get("maskingSequence"),
        "arms": [{"label": arm.get("label"), "type": arm.get("type"),
                  "interventions": [i.get("name") for i in arm.get("interventions", [])]}
                 for arm in arms.get("armGroups", [])],
        "interventions": [{"name": i.get("name"), "type": i.get("type")}
                          for i in arms.get("interventions", [])],
        "eligibility": {"sex": eligibility.get("sex"), "minimum_age": eligibility.get("minimumAge"),
                        "maximum_age": eligibility.get("maximumAge"),
                        "healthy_volunteers": eligibility.get("healthyVolunteers"),
                        "criteria": eligibility.get("eligibilityCriteria")},
        "primary_outcomes": [{"measure": o.get("measure"), "time_frame": o.get("timeFrame")}
                             for o in outcomes.get("primaryOutcomes", [])],
        "secondary_outcomes": [{"measure": o.get("measure"), "time_frame": o.get("timeFrame")}
                               for o in outcomes.get("secondaryOutcomes", [])],
        "has_results": has_results,
        "source_url": f"{BASE}/studies/{nct}",
        "study_url": f"https://clinicaltrials.gov/study/{nct}",
    }


TOOLS = (
    trial_search,
    trial_study,
)


def resource_catalog() -> dict:
    """List valid overall-status filter values and paging constraints."""
    return {"overall_status": sorted(STATUSES),
            "limit": "1-100 (pageSize)", "pagination": "opaque cursor via pageToken",
            "query_params": ["query.cond", "query.intr", "query.titles", "query.term"]}


RESOURCES = (
    ("clinicaltrials://statuses", resource_catalog),
)
