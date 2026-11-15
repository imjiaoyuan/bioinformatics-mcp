from common.serve import register, register_status
from mcp.server.mcpserver import MCPServer

from servers.kegg_mcp import api


mcp = MCPServer("kegg")

register(mcp, api, "kegg")
register_status(mcp, "kegg")


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
