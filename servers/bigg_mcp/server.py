from common.serve import register, register_status
from mcp.server.mcpserver import MCPServer

from servers.bigg_mcp import api


mcp = MCPServer("bigg")

register(mcp, api, "bigg")
register_status(mcp, "bigg")


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
