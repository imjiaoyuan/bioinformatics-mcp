from mcp.server.mcpserver import MCPServer

from servers.hpa_mcp import api


mcp = MCPServer("hpa")

for tool in api.TOOLS:
    mcp.add_tool(tool)

for uri, resource in api.RESOURCES:
    mcp.resource(uri)(resource)


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
