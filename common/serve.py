"""Aggregate selected provider tools into one MCP server process."""
from __future__ import annotations

from importlib import import_module

from mcp.server.fastmcp import FastMCP


def build(providers: list[str]) -> FastMCP:
    mcp = FastMCP("bioinformatics", instructions=f"Aggregated bioinformatics providers: {', '.join(providers)}")
    registered: set[str] = set()
    for provider in providers:
        api = import_module(f"servers.{provider}_mcp.api")
        for tool in api.TOOLS:
            if tool.__name__ in registered:
                raise ValueError(f"Duplicate tool {tool.__name__} from {provider}")
            mcp.add_tool(tool)
            registered.add(tool.__name__)
        for uri, resource in getattr(api, "RESOURCES", ()):
            mcp.resource(uri)(resource)
    return mcp


def main(providers: list[str]) -> None:
    build(providers).run()
