from common.serve import register, register_status
from mcp.server.mcpserver import MCPServer

from servers.msigdb_mcp import api


mcp = MCPServer("msigdb")

register(mcp, api, "msigdb")
register_status(mcp, "msigdb")


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
