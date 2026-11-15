from common.serve import register, register_status
from mcp.server.mcpserver import MCPServer

from servers.cellxgene_mcp import api


mcp = MCPServer("cellxgene")

register(mcp, api, "cellxgene")
register_status(mcp, "cellxgene")


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
