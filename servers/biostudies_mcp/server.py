from common.serve import register, register_status
from mcp.server.mcpserver import MCPServer

from servers.biostudies_mcp import api


mcp = MCPServer("biostudies")

register(mcp, api, "biostudies")
register_status(mcp, "biostudies")


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
