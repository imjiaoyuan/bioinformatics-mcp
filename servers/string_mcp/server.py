from mcp.server.mcpserver import MCPServer

from servers.string_mcp import api


mcp = MCPServer("string")

for tool in api.TOOLS:
    mcp.add_tool(tool)

for uri, resource in api.RESOURCES:
    mcp.resource(uri)(resource)


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
