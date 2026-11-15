from __future__ import annotations

from typing import Annotated

from pydantic import Field

from common.http import bounded, identifier, request, text

BASE = "https://api.anaconda.org"


def _name(value: str, name: str = "package") -> str:
    # Channel and package slugs are case-preserving but character-restricted.
    return identifier(value.strip(), r"[A-Za-z0-9_][A-Za-z0-9._-]*", name)


async def _get(path: str, params: dict | None = None):
    return (await request("GET", BASE + path, params=params)).json()


async def anaconda_search(query: str, limit: Annotated[int, Field(ge=1, le=100)] = 20) -> list[dict]:
    """Search public Anaconda packages and channels."""
    limit = bounded(limit, 100)
    data = await _get("/search", {"name": text(query)})
    return data[:limit] if isinstance(data, list) else data


async def anaconda_package(owner: str, package: str) -> dict:
    """Get package metadata, versions, platforms, and download counts."""
    return await _get(f"/package/{_name(owner, 'owner')}/{_name(package)}")


async def anaconda_files(owner: str, package: str, version: str | None = None) -> list[dict]:
    """List downloadable conda packages for an Anaconda package."""
    data = await anaconda_package(owner, package)
    files = data.get("files", []) if isinstance(data, dict) else []
    if version is not None:
        version = identifier(version, r"[A-Za-z0-9][A-Za-z0-9.+*_!-]*", "version")
        files = [x for x in files if x.get("version") == version]
    return files


TOOLS = (
    anaconda_search,
    anaconda_package,
    anaconda_files,
)


def resource_catalog() -> dict:
    """Describe Anaconda.org endpoints and parameter constraints."""
    return {"endpoints": {"/search?name=": "package/channel search (truncated locally to limit)",
                          "/package/{owner}/{package}": "package metadata",
                          "/package/{owner}/{package} (files key)": "downloadable conda files"},
            "limit": "1-100", "slug_format": "[A-Za-z0-9_][A-Za-z0-9._-]*"}


RESOURCES = (
    ("anaconda://endpoints", resource_catalog),
)
