from common.serve import register, register_status
from mcp.server.mcpserver import MCPServer

from servers.alliance_mcp import api


mcp = MCPServer("alliance")

register(mcp, api, "alliance")
register_status(mcp, "alliance")


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
