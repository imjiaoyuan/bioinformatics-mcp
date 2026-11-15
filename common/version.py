"""Installed and released version information shared by servers and doctor."""
from __future__ import annotations

import httpx
from importlib import metadata

PACKAGE = "bioinformatics-mcp"
RELEASES_URL = "https://api.github.com/repos/imjiaoyuan/bioinformatics-mcp/releases/latest"


def installed_version() -> str:
    return metadata.version(PACKAGE)


async def latest_version() -> str:
    from common.http import request
    response = await request("GET", RELEASES_URL, headers={"Accept": "application/vnd.github+json"},
                             interval=1.0, timeout=15.0)
    return response.json().get("tag_name", "").lstrip("v")


async def status_report(provider: str) -> dict:
    version = installed_version()
    report: dict = {"package": PACKAGE, "version": version, "provider": provider,
                    "update_command": "bioinformatics-mcp update"}
    try:
        latest = await latest_version()
    except (httpx.HTTPError, ValueError, KeyError) as error:
        report["latest"] = f"unavailable: {type(error).__name__}: {error}"
    else:
        report["latest"] = latest
        report["outdated"] = bool(latest) and latest != version
    return report
