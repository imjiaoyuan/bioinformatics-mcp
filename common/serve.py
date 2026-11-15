"""Aggregate selected provider tools into one MCP server process."""
from __future__ import annotations

from importlib import import_module
from types import ModuleType

from mcp.server.mcpserver import MCPServer
from mcp.types import ToolAnnotations

from common.version import status_report

# Every provider tool queries public data services; the only exceptions are
# long-running submissions, listed per provider in ``api.MUTATING``.
READ_ONLY_TOOLS = ToolAnnotations(read_only_hint=True, open_world_hint=True)


def register(mcp: MCPServer, api: ModuleType, provider: str,
             registered: dict[str, str] | None = None) -> None:
    """Register one provider's tools and resources on an MCP server.

    When aggregating, a tool name that another provider already registered is
    namespaced as ``{provider}_{tool}`` instead of failing startup; both tools
    stay callable and the clash is visible in the description.
    """
    seen = registered if registered is not None else {}
    mutating = set(getattr(api, "MUTATING", ()))
    for tool in api.TOOLS:
        annotations = None if tool.__name__ in mutating else READ_ONLY_TOOLS
        if tool.__name__ in seen:
            mcp.add_tool(tool, name=f"{provider}_{tool.__name__}",
                         description=f"[{provider}] {tool.__doc__ or tool.__name__}",
                         annotations=annotations)
        else:
            mcp.add_tool(tool, annotations=annotations)
        seen.setdefault(tool.__name__, provider)
    for uri, resource in getattr(api, "RESOURCES", ()):
        mcp.resource(uri)(resource)


def register_status(mcp: MCPServer, provider: str) -> None:
    """Expose installed/latest version information as ``meta://status``."""
    async def status() -> dict:
        return await status_report(provider)
    mcp.resource("meta://status")(status)


def build(providers: list[str]) -> MCPServer:
    mcp = MCPServer("bioinformatics", instructions=f"Aggregated bioinformatics providers: {', '.join(providers)}")
    registered: dict[str, str] = {}
    for provider in providers:
        api = import_module(f"servers.{provider}_mcp.api")
        register(mcp, api, provider, registered)
    register_status(mcp, ",".join(providers))
    return mcp


def main(providers: list[str]) -> None:
    build(providers).run()
