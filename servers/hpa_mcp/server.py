from mcp.server.fastmcp import FastMCP

from servers.hpa_mcp import api


mcp = FastMCP("hpa")

for tool in api.TOOLS:
    mcp.add_tool(tool)

for uri, resource in api.RESOURCES:
    mcp.resource(uri)(resource)


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
