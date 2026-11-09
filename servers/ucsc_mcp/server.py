"""UCSC Genome Browser genomes, track metadata and chromosomal range data."""
from __future__ import annotations

from mcp.server.fastmcp import FastMCP

from common.api import json_response
from common.http import bounded, identifier, text

mcp = FastMCP("ucsc")
BASE = "https://api.genome.ucsc.edu"

_CHROM = r"chr[A-Za-z0-9_.:-]+"


async def _get(path: str, params: dict) -> dict:
    data, source = await json_response(f"{BASE}/{path}", params)
    return {**source, **data}


@mcp.tool()
async def ucsc_list_genomes() -> dict:
    """List all UCSC Genome Browser assemblies with their scientific names and dates."""
    return await _get("list/ucscGenomes", {})


@mcp.tool()
async def ucsc_list_tracks(genome: str) -> dict:
    """List available tracks, groups and composite settings for one assembly."""
    return await _get("list/tracks", {"genome": identifier(genome, r"[A-Za-z0-9_.+-]+", "genome")})


@mcp.tool()
async def ucsc_list_chromosomes(genome: str) -> dict:
    """List chromosome names and lengths for one assembly."""
    return await _get("list/chromosomes", {"genome": identifier(genome, r"[A-Za-z0-9_.+-]+", "genome")})


@mcp.tool()
async def ucsc_get_data(genome: str, track: str, chrom: str, start: int, end: int) -> dict:
    """Retrieve track records intersecting one chromosomal range (0-based half-open).

    Keep ranges narrow: UCSC caps the returned interval span, and very large
    requests may be truncated or rejected by the upstream API.
    """
    genome = identifier(genome, r"[A-Za-z0-9_.+-]+", "genome")
    track = identifier(track, r"[A-Za-z0-9_.+-]+", "track")
    chrom = identifier(chrom, _CHROM, "chrom")
    start = bounded(start, 2_500_000_000, "start", 0)
    end = bounded(end, 2_500_000_000, "end", 0)
    if end <= start:
        raise ValueError("end must be greater than start")
    return await _get("getData/track", {"genome": genome, "track": track, "chrom": chrom,
                                        "start": start, "end": end})


@mcp.tool()
async def ucsc_search_genomes(name: str) -> dict:
    """List assemblies whose name or scientific name matches a substring (case-insensitive)."""
    query = text(name, "name", 100).lower()
    data = await _get("list/ucscGenomes", {})
    genomes = {key: value for key, value in data.get("ucscGenomes", {}).items()
               if query in key.lower()
               or query in str(value.get("name", "")).lower()
               or query in str(value.get("organism", "")).lower()}
    return {**data, "ucscGenomes": genomes, "matched": len(genomes)}


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
