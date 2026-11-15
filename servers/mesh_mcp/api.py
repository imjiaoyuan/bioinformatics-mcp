"""MeSH (Medical Subject Headings) descriptor lookups via the NLM RDF service.

Upstream notes, verified live:
- ``GET /mesh/lookup/descriptor?label=...&match=exact|contains`` returns a plain
  JSON array of ``{"resource", "label"}`` (unpaginated; ``contains`` appears
  capped at 10 hits upstream).
- ``GET /mesh/{id}`` content-negotiates: with ``Accept: application/rdf+xml`` it
  returns a small RDF/XML document. Plain ``Accept: application/json`` answers
  with N-Triples text, not JSON, so RDF/XML is parsed instead. Unknown ids
  answer HTTP 200 with an empty RDF graph, not 404. Records seen: D =
  ``TopicalDescriptor``, Q = ``Qualifier``, C = ``SCR_*`` supplementary concept.
- ``/mesh/sparql`` accepts ``format=application/sparql-results+json``; the
  undated (``/mesh/...``) graph is a subset of the dated per-year graphs, but it
  carries labels, tree numbers and parent tree numbers, which is all the tools
  below need. SPARQL literals carry ``@en`` language tags, so filters compare
  ``STR()`` values.

No separate ``mesh_search`` tool is exposed: ``mesh_lookup(..., match="contains")``
already performs substring search over descriptor labels through the lookup
service, so a SPARQL contains-search would duplicate it.
"""
from __future__ import annotations
from xml.etree import ElementTree
from typing import Any

from common.api import choice, json_response, local_page, page
from common.http import identifier, request, safe_url, text

BASE = "https://id.nlm.nih.gov/mesh"
ENDPOINT = f"{BASE}/sparql"
FORMAT = "application/sparql-results+json"
ID_PATTERN = r"[DCQ][0-9]{6}"
SPARQL_LIMIT = 1000

PREFIXES = """\
PREFIX meshv: <http://id.nlm.nih.gov/mesh/vocab#>
PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
"""


def _mesh_id(value: str) -> str:
    return identifier(value.upper(), ID_PATTERN, "mesh_id")


def _uri(mesh_id: str) -> str:
    return f"{BASE}/{mesh_id}"


async def _sparql(select: str, where: str) -> dict:
    query = f"{PREFIXES}SELECT DISTINCT {select} WHERE {{ {where} }} LIMIT {SPARQL_LIMIT}"
    data, source = await json_response(
        ENDPOINT, {"query": query, "format": FORMAT}, interval=1.0)
    rows = [{variable: bound["value"] for variable, bound in binding.items()}
            for binding in data.get("results", {}).get("bindings", [])]
    return {**source, "sparql": query, "rows": rows}


async def _tree_codes(mesh_ids: list[str]) -> dict[str, list[str]]:
    """Map descriptor ids to their undated tree number codes via one SPARQL query."""
    values = " ".join(f"<{_uri(mesh_id)}>" for mesh_id in sorted(mesh_ids))
    data = await _sparql(
        "?d ?code",
        f"VALUES ?d {{ {values} }} "
        "?d meshv:treeNumber ?tn . ?tn rdfs:label ?code .")
    codes: dict[str, list[str]] = {}
    for row in data["rows"]:
        codes.setdefault(row["d"].rsplit("/", 1)[-1], []).append(row["code"])
    return codes


async def mesh_lookup(label: str, match: str = "exact", limit: int = 20,
                      offset: int = 0) -> dict:
    """Look up MeSH descriptors by label with exact or contains matching.

    Uses the NLM label lookup service; each hit is enriched with its tree
    number codes through one SPARQL query. Upstream caps ``contains`` matches
    at 10 hits, so results are paginated locally over that short list.
    """
    label = text(label, "label", 150)
    match = choice(match, {"contains", "exact"}, "match")
    paging = page(limit, offset)
    data, source = await json_response(
        f"{BASE}/lookup/descriptor", {"label": label, "match": match})
    hits = [{"mesh_id": item["resource"].rsplit("/", 1)[-1], "label": item["label"]}
            for item in data if isinstance(item, dict) and item.get("resource")]
    codes = await _tree_codes([hit["mesh_id"] for hit in hits]) if hits else {}
    rows = [{**hit, "tree_numbers": sorted(codes.get(hit["mesh_id"], []))} for hit in hits]
    return {**source, "label": label, "match": match,
            **local_page(rows, paging["limit"], paging["offset"])}


def _local(name: str) -> str:
    return name.rsplit("}", 1)[-1]


def _parse_detail(content: bytes, source_url: str) -> dict:
    """Parse the RDF/XML detail graph defensively into a flat record.

    Responses are JSON-LD-shaped RDF served as XML; unknown ids return an empty
    graph with HTTP 200, which is reported as unknown rather than silently
    empty. Every remaining predicate is kept under its local name so schema
    additions upstream stay visible.
    """
    try:
        graph = ElementTree.fromstring(content)
    except ElementTree.ParseError:
        raise ValueError(f"Malformed RDF response from {source_url}") from None
    node = next(iter(graph), None)
    if node is None:
        raise ValueError(f"Unknown MeSH record: no RDF data returned by {source_url}")
    properties: dict[str, list[str]] = {}
    for predicate in node:
        value = predicate.get(f"{{http://www.w3.org/1999/02/22-rdf-syntax-ns#}}resource")
        if value is None:
            value = (predicate.text or "").strip()
        properties.setdefault(_local(predicate.tag), []).append(value)
    return {"record_type": _local(node.tag),
            "uri": node.get("{http://www.w3.org/1999/02/22-rdf-syntax-ns#}about", source_url),
            "properties": properties}


async def mesh_entry(mesh_id: str) -> dict:
    """Retrieve one MeSH record by id: descriptor (D), qualifier (Q) or
    supplementary concept (C).

    Fetches the RDF/XML detail graph for the id; unknown ids are reported as
    errors even though upstream answers HTTP 200 with an empty graph.
    """
    mesh_id = _mesh_id(mesh_id)
    response = await request("GET", _uri(mesh_id),
                             headers={"Accept": "application/rdf+xml"}, interval=1.0)
    source_url = safe_url(response.url)
    record = _parse_detail(response.content, source_url)
    properties = record.pop("properties")
    label = properties.pop("label", [None])[0]
    return {**record, "source_url": source_url, "mesh_id": mesh_id, "label": label,
            "tree_numbers": sorted({value.rsplit("/", 1)[-1]
                                    for value in properties.pop("treeNumber", [])}),
            "properties": properties}


async def mesh_tree(mesh_id: str, limit: int = 20, offset: int = 0) -> dict:
    """List tree positions and their parents for one MeSH descriptor.

    Resolves the descriptor's tree number roots and walks their subtree in the
    undated RDF graph via SPARQL. The upstream query is capped at 1000 rows and
    results are paginated locally over it.
    """
    mesh_id = identifier(mesh_id.upper(), r"D[0-9]{6}", "mesh_id")
    paging = page(limit, offset)
    where = (f"?descriptor meshv:treeNumber ?root . ?root rdfs:label ?rootCode . "
             f"{{ BIND(?root AS ?position) }} UNION "
             f"{{ ?position meshv:parentTreeNumber+ ?root . "
             f"FILTER (!REGEX(STR(?position), \"/mesh/[0-9]{{4}}/\")) }} "
             f"?position rdfs:label ?code . "
             f"OPTIONAL {{ ?position meshv:parentTreeNumber ?parent . "
             f"?parent rdfs:label ?parentCode . }}")
    data = await _sparql("?root ?code ?parentCode", where)
    rows = [{"position": row.get("code"), "parent": row.get("parentCode"),
             "root": row.get("root") is not None and row.get("code")}
            for row in data.pop("rows")]
    return {**data, "mesh_id": mesh_id, "query_limit": SPARQL_LIMIT,
            **local_page(rows, paging["limit"], paging["offset"])}


TOOLS = (
    mesh_lookup,
    mesh_entry,
    mesh_tree,
)

RESOURCES = ()
