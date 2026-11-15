from common.serve import register, register_status
from mcp.server.mcpserver import MCPServer

from servers.string_mcp import api


mcp = MCPServer("string")

register(mcp, api, "string")
register_status(mcp, "string")


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
