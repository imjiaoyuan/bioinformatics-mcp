from mcp.server.mcpserver import MCPServer

from servers.gwas_mcp import api


mcp = MCPServer("gwas")

for tool in api.TOOLS:
    mcp.add_tool(tool)

for uri, resource in api.RESOURCES:
    mcp.resource(uri)(resource)


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
