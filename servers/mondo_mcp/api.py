"""MONDO disease ontology: label search, entries and cross-references.

Upstream caveat: MONDO exposes no queryable REST API. The stable public
endpoint is the dated ontology release JSON published via the purl
redirect (currently mirrored as a GitHub release asset). It is fetched
in memory with a bounded response size, parsed once per process, and
sliced locally; values therefore reflect that release snapshot, not a
live database view. No HTML scraping and no files are written to disk.
"""
from __future__ import annotations

import asyncio
from typing import Any

from common.api import local_page
from common.http import identifier, request, text

ONTOLOGY_URL = "https://purl.obolibrary.org/obo/mondo.json"
MAX_BYTES = 250_000_000
PREFIX = "http://purl.obolibrary.org/obo/"

_ontology: dict[str, Any] | None = None
_lock = asyncio.Lock()


def _mondo_id(iri: str) -> str:
    return iri.removeprefix(PREFIX).replace("_", ":", 1)


async def _load() -> dict[str, Any]:
    global _ontology
    if _ontology is not None:
        return _ontology
    async with _lock:
        if _ontology is None:
            response = await request("GET", ONTOLOGY_URL, max_bytes=MAX_BYTES)
            release = response.json()
            entries: dict[str, dict[str, Any]] = {}
            for node in release["graphs"][0].get("nodes", []):
                if node.get("type") != "CLASS" or "lbl" not in node:
                    continue
                mondo_id = _mondo_id(node["id"])
                meta = node.get("meta") or {}
                definition = meta.get("definition") or {}
                entries[mondo_id] = {
                    "mondo_id": mondo_id,
                    "label": node["lbl"],
                    "definition": definition.get("val"),
                    "definition_xrefs": sorted(definition.get("xrefs") or []),
                    "synonyms": [{"synonym": item.get("val"), "scope": item.get("pred")}
                                 for item in meta.get("synonyms") or []],
                    "xrefs": sorted({item.get("val") for item in meta.get("xrefs") or [] if item.get("val")}),
                    "subsets": sorted(meta.get("subsets") or []),
                    "comments": list(meta.get("comments") or []),
                    "obsolete": bool(meta.get("deprecated")),
                }
            children: dict[str, set[str]] = {}
            for edge in release["graphs"][0].get("edges", []):
                if edge.get("pred") == "is_a":
                    children.setdefault(_mondo_id(edge["obj"]), set()).add(_mondo_id(edge["sub"]))
            _ontology = {"entries": entries,
                         "children": {key: sorted(values) for key, values in children.items()},
                         "source_url": str(response.url)}
            release = None
    return _ontology


def _id(value: str) -> str:
    return identifier(value.upper(), r"MONDO:[0-9]{7}", "MONDO ID")


def _entry(ontology: dict[str, Any], value: str) -> dict[str, Any]:
    entry = ontology["entries"].get(_id(value))
    if entry is None:
        raise ValueError(f"Unknown MONDO ID in this release: {value}")
    return entry


def _matches(entry: dict[str, Any], needle: str) -> bool:
    haystack = " ".join([entry["label"], *(item["synonym"] or "" for item in entry["synonyms"])])
    return needle in haystack.lower()


async def mondo_search(query: str, limit: int = 20, offset: int = 0) -> dict:
    """Search disease labels and synonyms by case-insensitive substring.

    Matches the downloaded MONDO release snapshot locally and paginates it
    client-side; match fields are returned per hit.
    """
    needle = text(query, "query", 150).lower()
    ontology = await _load()
    matched = []
    for entry in sorted(ontology["entries"].values(), key=lambda item: item["mondo_id"]):
        if _matches(entry, needle):
            hits = [item["synonym"] for item in entry["synonyms"] if needle in (item["synonym"] or "").lower()]
            matched.append({"mondo_id": entry["mondo_id"], "label": entry["label"],
                            "matched_in": "label" if needle in entry["label"].lower() else "synonym",
                            "matched_synonyms": hits})
    return local_page(matched, limit, offset, source_url=ontology["source_url"],
                      release_url=ONTOLOGY_URL, query=query)


async def mondo_entry(mondo_id: str) -> dict:
    """Retrieve one disease entry with label, definition, synonyms, xrefs and subsets.

    Values come from the downloaded MONDO release snapshot; unknown IDs raise.
    """
    ontology = await _load()
    entry = _entry(ontology, mondo_id)
    return {"source_url": ontology["source_url"], **entry}


async def mondo_xrefs(mondo_id: str) -> dict:
    """List the external database cross-references recorded for one disease.

    Cross-references are returned exactly as curated in the MONDO release.
    """
    ontology = await _load()
    entry = _entry(ontology, mondo_id)
    return {"source_url": ontology["source_url"], "mondo_id": entry["mondo_id"],
            "label": entry["label"], "xrefs": entry["xrefs"], "total": len(entry["xrefs"])}


async def mondo_xref_lookup(xref: str, limit: int = 20, offset: int = 0) -> dict:
    """Reverse-lookup MONDO diseases by an external cross-reference, e.g. OMIM:125853.

    The reference is matched case-insensitively against the release snapshot.
    """
    reference = identifier(xref.upper(), r"[A-Z][A-Z0-9_]*:[A-Za-z0-9_.-]+", "cross-reference")
    ontology = await _load()
    matched = [{"mondo_id": entry["mondo_id"], "label": entry["label"]}
               for entry in sorted(ontology["entries"].values(), key=lambda item: item["mondo_id"])
               if reference in (value.upper() for value in entry["xrefs"])]
    return local_page(matched, limit, offset, source_url=ontology["source_url"], xref=reference)


async def mondo_children(mondo_id: str, limit: int = 20, offset: int = 0) -> dict:
    """List the direct subclasses of one disease from the release is_a edges.

    Only direct children are returned; use mondo_entry for the parent itself.
    """
    ontology = await _load()
    parent = _entry(ontology, mondo_id)
    rows = [{"mondo_id": child, "label": ontology["entries"].get(child, {}).get("label")}
            for child in ontology["children"].get(parent["mondo_id"], [])]
    return local_page(rows, limit, offset, source_url=ontology["source_url"],
                      mondo_id=parent["mondo_id"], label=parent["label"])


TOOLS = (
    mondo_search,
    mondo_entry,
    mondo_xrefs,
    mondo_xref_lookup,
    mondo_children,
)


RESOURCES = ()
