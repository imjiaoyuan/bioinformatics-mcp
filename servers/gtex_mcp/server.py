from common.serve import register, register_status
from mcp.server.mcpserver import MCPServer

from servers.gtex_mcp import api


mcp = MCPServer("gtex")

register(mcp, api, "gtex")
register_status(mcp, "gtex")


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
