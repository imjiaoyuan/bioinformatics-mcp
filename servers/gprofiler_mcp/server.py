"""g:Profiler enrichment, identifier conversion and ortholog mapping."""
from __future__ import annotations

from mcp.server.fastmcp import FastMCP

from common.http import bounded, identifier, identifiers, request

mcp = FastMCP("gprofiler")
BASE = "https://biit.cs.ut.ee/gprofiler/api"
SOURCES = {"GO:BP", "GO:MF", "GO:CC", "REAC", "WP", "HP", "CORUM", "KEGG"}


async def _post(path: str, body: dict, limit: int) -> dict:
    url = f"{BASE}/{path}/"
    data = (await request("POST", url, json=body)).json()
    if not isinstance(data, dict) or not isinstance(data.get("result"), list):
        raise ValueError("g:Profiler returned an unexpected response")
    rows = data["result"]
    return {"result": rows[:limit], "total_results": len(rows), "truncated": len(rows) > limit,
            "meta": data.get("meta", {}), "source_url": url}


@mcp.tool()
async def gprofiler_enrichment(genes: list[str], organism: str = "hsapiens",
                               sources: list[str] | None = None, background: list[str] | None = None,
                               threshold: float = 0.05, correction: str = "g_SCS", limit: int = 100) -> dict:
    """Run functional enrichment, optionally against the experimentally detected gene background."""
    bounded(limit, 500)
    sources = sources if sources is not None else ["GO:BP", "GO:MF", "GO:CC"]
    if not sources or len(sources) > len(SOURCES) or any(s not in SOURCES for s in sources):
        raise ValueError(f"sources must be a nonempty subset of {sorted(SOURCES)}")
    if not 0 < threshold <= 1 or correction not in {"g_SCS", "fdr", "bonferroni"}:
        raise ValueError("Invalid threshold or correction")
    body = {"query": identifiers(genes), "organism": identifier(organism), "sources": sources,
            "user_threshold": threshold, "significance_threshold_method": correction,
            "no_evidences": True}
    if background is not None:
        body.update(background=identifiers(background, 10000), domain_scope="custom")
    return await _post("gost/profile", body, limit)


@mcp.tool()
async def gprofiler_convert(genes: list[str], organism: str = "hsapiens", target: str = "ENTREZGENE_ACC",
                            limit: int = 100) -> dict:
    """Convert a list of gene identifiers; retain unmapped and ambiguous mappings."""
    bounded(limit, 1000)
    if target not in {"ENTREZGENE_ACC", "ENSG", "UNIPROTSWISSPROT"}:
        raise ValueError("target must be ENTREZGENE_ACC, ENSG or UNIPROTSWISSPROT")
    return await _post("convert/convert", {"query": identifiers(genes), "organism": identifier(organism),
                                          "target": identifier(target)}, limit)


@mcp.tool()
async def gprofiler_orthologs(genes: list[str], organism: str = "hsapiens",
                             target_organism: str = "mmusculus", limit: int = 100) -> dict:
    """Map genes to orthologs in another supported organism; preserve one-to-many results."""
    bounded(limit, 1000)
    return await _post("orth/orth", {"query": identifiers(genes), "organism": identifier(organism),
                                    "target": identifier(target_organism)}, limit)


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
