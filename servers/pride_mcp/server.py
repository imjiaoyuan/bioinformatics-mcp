from common.serve import register, register_status
from mcp.server.mcpserver import MCPServer

from servers.pride_mcp import api


mcp = MCPServer("pride")

register(mcp, api, "pride")
register_status(mcp, "pride")


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
