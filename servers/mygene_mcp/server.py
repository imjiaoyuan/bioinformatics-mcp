"""MyGene.info gene query/annotation and MyVariant.info variant annotation."""
from __future__ import annotations

from urllib.parse import quote

from mcp.server.fastmcp import FastMCP

from common.http import bounded, identifier, identifiers, request, text

mcp = FastMCP("mygene")
GENE_BASE = "https://api.mygene.info/v3"
VARIANT_BASE = "https://api.myvariant.info/v1"
VARIANT_ID = r"[A-Za-z0-9_.:+><=-]+"


async def _get(url: str, params: dict) -> dict:
    response = await request("GET", url, params={k: v for k, v in params.items() if v is not None})
    return {**response.json(), "source_url": str(response.url)}


async def _post(url: str, data: dict) -> dict:
    """Send a form-encoded batch request, as required by both services."""
    response = await request("POST", url, data=data, retryable=True)
    body = response.json()
    results = body.get("hits", body) if isinstance(body, dict) else body
    return {"source_url": str(response.url), "results": results}


def _fields(value: str | None) -> str | None:
    return text(value, "fields", 500) if value is not None else None


@mcp.tool()
async def mygene_query(query: str, fields: str | None = None, species: str | None = None,
                       limit: int = 10, skip: int = 0) -> dict:
    """Search genes across all fields or fielded queries (e.g. symbol:cdk2).

    Supports MyGene.info query syntax, including wildcards, booleans and
    genome intervals; species accepts common names or taxonomy ids.
    """
    params = {"q": text(query, "query", 1000), "size": bounded(limit),
              "from": bounded(skip, 1_000_000, "skip", 0),
              "fields": _fields(fields), "species": text(species, "species", 200) if species else None}
    return await _get(f"{GENE_BASE}/query", params)


@mcp.tool()
async def mygene_gene(gene_id: str, fields: str | None = None) -> dict:
    """Retrieve one gene annotation by Entrez or Ensembl gene id.

    Pass a comma-separated fields list (dot notation supported, e.g.
    "refseq.rna") or fields=all; default returns a compact set of fields.
    """
    params = {"fields": _fields(fields)}
    return await _get(f"{GENE_BASE}/gene/{identifier(gene_id, name='gene id')}", params)


@mcp.tool()
async def mygene_batch(ids: list[str], scopes: str = "entrezgene,ensemblgene,retired",
                       fields: str | None = None, species: str | None = None) -> dict:
    """Batch-resolve up to 100 gene identifiers to annotations via POST /query.

    Each returned item echoes its "query" term; unmatched terms carry
    "notfound": true. Use scopes to select the input id type(s).
    """
    return await _post(f"{GENE_BASE}/query", {
        "q": ",".join(identifiers(ids, 100)), "scopes": text(scopes, "scopes", 200),
        "fields": _fields(fields), "species": text(species, "species", 200) if species else None})


@mcp.tool()
async def myvariant_variant(variant_id: str, fields: str | None = None) -> dict:
    """Retrieve one variant annotation by HGVS id (hg19 genomic coordinates).

    The id uses HGVS syntax such as chr1:g.35367G>A; pass a comma-separated
    fields list (dot notation supported, e.g. "cadd.gene") or fields=all.
    """
    url = f"{VARIANT_BASE}/variant/{quote(identifier(variant_id, VARIANT_ID, 'variant id'), safe=':,.-_')}"
    return await _get(url, {"fields": _fields(fields)})


@mcp.tool()
async def myvariant_batch(ids: list[str], fields: str | None = None) -> dict:
    """Batch-annotate up to 100 HGVS variant ids via POST /variant.

    Each returned item echoes its "query" term; unmatched ids carry
    "notfound": true. Choose fields to keep responses small.
    """
    values = identifiers(ids, 100)
    for value in values:
        identifier(value, VARIANT_ID, "variant id")
    return await _post(f"{VARIANT_BASE}/variant",
                       {"ids": ",".join(values), "fields": _fields(fields)})


@mcp.tool()
async def mygene_metadata() -> dict:
    """Retrieve MyGene.info service metadata: available species and data build.

    Use it to confirm supported taxonomy ids and the current data version
    before running queries.
    """
    return await _get(f"{GENE_BASE}/metadata", {})


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
