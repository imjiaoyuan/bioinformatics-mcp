from common.serve import register, register_status
from mcp.server.mcpserver import MCPServer

from servers.pdbe_mcp import api


mcp = MCPServer("pdbe")

register(mcp, api, "pdbe")
register_status(mcp, "pdbe")


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
