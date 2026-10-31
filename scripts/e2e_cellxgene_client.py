"""End-to-end MCP client checks for the CELLxGENE servers.

Spawns the installed cellxgene-mcp console script exactly the way an MCP
client (Claude Code, Codex, yak, ...) would: stdio transport, initialize,
list tools, then live tool calls. Two paths are covered:

- REST baseline (no SDK, any Python): run with the base environment
    .venv/bin/python scripts/e2e_cellxgene_client.py
- SDK deep queries (Python 3.10-3.13 with '.[cellxgene]'): run with the SDK
  environment, which also exercises REST tools first
    .venv-cellxgene/bin/python scripts/e2e_cellxgene_client.py

Both scripts contact the live public APIs and exit non-zero on failure.
"""
import asyncio
import json
import sys
from pathlib import Path

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


def obj(text: str):
    return json.loads(text)


async def check_rest_tools(session: ClientSession, have_sdk: bool) -> list[str]:
    failures: list[str] = []

    async def call(tool: str, arguments: dict, check=lambda t: None) -> None:
        result = await session.call_tool(tool, arguments)
        shown = ", ".join(f"{k}={v!r}" for k, v in arguments.items())
        summary = result.content[0].text[:160].replace("\n", " ") if result.content else ""
        print(f"[{'ERROR' if result.isError else 'ok '}] {tool}({shown})\n      {summary}")
        if result.isError:
            failures.append(tool)
        else:
            check(result.content[0].text)

    await call("cellxgene_versions", {},
               lambda t: obj(t)["aliases"]["stable"] or (_ for _ in ()).throw(AssertionError("no stable alias")))
    await call("cellxgene_datasets", {"organism": "Homo sapiens", "tissue": "lung", "limit": 3},
               lambda t: obj(t)["results"][0]["dataset_id"])
    await call("cellxgene_dataset_url", {"dataset_id": "00099d5e-154f-4a7a-aa8d-fa30c8c0c43c"},
               lambda t: obj(t)["h5ad_uri"].startswith("s3://"))
    if not have_sdk:
        # SDK-only tools must fail cleanly with guidance, not crash the server.
        await call("cellxgene_cells", {})
        if "cellxgene_cells" in failures and have_sdk is False:
            message = (await session.call_tool("cellxgene_cells", {})).content[0].text
            if "cellxgene-census SDK" in message:
                failures.remove("cellxgene_cells")
                print("      (expected without SDK: clean guidance error)")
    return failures


async def check_sdk_tools(session: ClientSession) -> list[str]:
    failures: list[str] = []
    # Page through coordinate windows; the first lung cells appear around joinid 30k.
    after, cells, version = -1, [], None
    for _ in range(8):
        result = await session.call_tool("cellxgene_cells",
                                         {"tissue": "lung", "limit": 2, "scan_size": 10000,
                                          "after_joinid": after})
        if result.isError:
            print("[ERROR] cellxgene_cells:", result.content[0].text[:200])
            return ["cellxgene_cells"]
        data = obj(result.content[0].text)
        version, after = data["census_version"], data["next_after_joinid"]
        cells.extend(data["results"])
        print(f"[ok ] cellxgene_cells window [{data['scan_start']},{data['scan_end']}] "
              f"+{len(data['results'])} rows, next={after}")
        if cells:
            break
    if not cells:
        failures.append("cellxgene_cells")
    else:
        print("      first cell:", {k: cells[0][k] for k in ("soma_joinid", "tissue")})
        result = await session.call_tool("cellxgene_expression",
                                         {"cell_ids": [c["soma_joinid"] for c in cells[:2]],
                                          "gene_ids": ["ENSG00000141510"], "version": version})
        if result.isError or not obj(result.content[0].text)["matrix"]:
            failures.append("cellxgene_expression")
        else:
            print("[ok ] cellxgene_expression matrix:", obj(result.content[0].text)["matrix"])
    return failures


async def main() -> int:
    command = Path(sys.executable).parent / "cellxgene-mcp"
    if not command.is_file():
        print(f"FAIL: console script not found: {command}")
        return 1
    try:
        import cellxgene_census  # noqa: F401
        have_sdk = True
    except ImportError:
        have_sdk = False
    print(f"client python: {sys.version.split()[0]} | SDK installed: {have_sdk}")

    params = StdioServerParameters(command=str(command), cwd=str(Path.cwd().parent))
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            info = await session.initialize()
            names = sorted(t.name for t in (await session.list_tools()).tools)
            print(f"connected: server={info.serverInfo.name} protocol={info.protocolVersion}")
            print(f"tools ({len(names)}): {', '.join(names)}")
            failures = await check_rest_tools(session, have_sdk)
            if have_sdk:
                failures += await check_sdk_tools(session)
    print("E2E:", "FAILED " + str(failures) if failures else "PASSED")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(asyncio.run(asyncio.wait_for(main(), timeout=1500)))
