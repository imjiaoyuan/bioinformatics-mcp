from common.serve import register, register_status
from mcp.server.mcpserver import MCPServer

from servers.gwas_mcp import api


mcp = MCPServer("gwas")

register(mcp, api, "gwas")
register_status(mcp, "gwas")


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
