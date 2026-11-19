from common.serve import register, register_status
from mcp.server.mcpserver import MCPServer

from servers.jaspar_mcp import api


mcp = MCPServer("jaspar")

register(mcp, api, "jaspar")
register_status(mcp, "jaspar")


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
