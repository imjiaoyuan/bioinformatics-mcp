"""Typed, bounded Open Targets Platform GraphQL queries."""
from __future__ import annotations

from mcp.server.fastmcp import FastMCP

from common.api import choice, json_response
from common.http import bounded, identifier, text

mcp = FastMCP("opentargets")
BASE = "https://api.platform.opentargets.org/api/v4/graphql"
META = "meta { dataVersion { year month iteration } apiVersion { x y z } }"


def _target(value: str) -> str:
    return identifier(value.upper(), r"ENSG[0-9]{11}", "human Ensembl gene ID")


def _disease(value: str) -> str:
    return identifier(value, r"[A-Za-z][A-Za-z0-9]*_[0-9]+", "disease ontology ID")


def _page(limit: int, page: int) -> dict:
    return {"size": bounded(limit), "index": bounded(page, 10000, "page", 0)}


async def _query(declarations: str, selection: str, variables: dict) -> dict:
    query = f"query({declarations}) {{ {META} {selection} }}"
    result, source = await json_response(BASE, body={"query": query, "variables": variables})
    errors = result.get("errors", [])
    return {**source, "status": ("partial" if result.get("data") else "error") if errors else "ok",
            "data": result.get("data"), "errors": errors}


@mcp.tool()
async def opentargets_search(query: str, entity: str = "target", limit: int = 20,
                             page: int = 0) -> dict:
    """Search target, disease or drug entities; return IDs for subsequent typed queries."""
    choice(entity, {"target", "disease", "drug"}, "entity")
    return await _query("$query: String!, $entities: [String!], $page: Pagination",
                        "search(queryString: $query, entityNames: $entities, page: $page) { total hits { id name entity description score } }",
                        {"query": text(query), "entities": [entity], "page": _page(limit, page)})


@mcp.tool()
async def opentargets_target(target_id: str) -> dict:
    """Retrieve a human target's annotation, function and tractability assessments."""
    return await _query("$id: String!", "target(ensemblId: $id) { id approvedSymbol approvedName functionDescriptions tractability { label modality value } }",
                        {"id": _target(target_id)})


@mcp.tool()
async def opentargets_disease(disease_id: str) -> dict:
    """Retrieve a disease/phenotype and its immediate ontology relationships."""
    return await _query("$id: String!", "disease(efoId: $id) { id name description therapeuticAreas { id name } parents { id name } }",
                        {"id": _disease(disease_id)})


@mcp.tool()
async def opentargets_associations(target_id: str | None = None, disease_id: str | None = None,
                                   limit: int = 20, page: int = 0) -> dict:
    """Rank diseases for one target or targets for one disease, retaining datasource scores."""
    if (target_id is None) == (disease_id is None):
        raise ValueError("Provide exactly one of target_id and disease_id")
    if target_id is not None:
        selection = "target(ensemblId: $id) { id associatedDiseases(page: $page) { count rows { score disease { id name } datasourceScores { id score } } } }"
        value = _target(target_id)
    else:
        selection = "disease(efoId: $id) { id associatedTargets(page: $page) { count rows { score target { id approvedSymbol } datasourceScores { id score } } } }"
        value = _disease(disease_id)
    return await _query("$id: String!, $page: Pagination", selection,
                        {"id": value, "page": _page(limit, page)})


@mcp.tool()
async def opentargets_drug(chembl_id: str) -> dict:
    """Retrieve a drug's annotation and current maximum clinical stage."""
    value = identifier(chembl_id.upper(), r"CHEMBL[0-9]+", "ChEMBL ID")
    return await _query("$id: String!", "drug(chemblId: $id) { id name description drugType maximumClinicalStage }",
                        {"id": value})


@mcp.tool()
async def opentargets_evidence(target_id: str, disease_id: str, limit: int = 20,
                               cursor: str | None = None) -> dict:
    """Retrieve supporting evidence for a target-disease pair, preserving the next cursor."""
    variables = {"target": _target(target_id), "diseases": [_disease(disease_id)],
                 "size": bounded(limit), "cursor": text(cursor, "cursor", 4000) if cursor is not None else None}
    return await _query("$target: String!, $diseases: [String!]!, $size: Int, $cursor: String",
                        "target(ensemblId: $target) { id evidences(efoIds: $diseases, size: $size, cursor: $cursor) { count cursor rows { id datasourceId datatypeId score literature } } }",
                        variables)


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
