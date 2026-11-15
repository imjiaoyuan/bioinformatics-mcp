from common.serve import register, register_status
from mcp.server.mcpserver import MCPServer

from servers.ensembl_mcp import api


mcp = MCPServer("ensembl")

register(mcp, api, "ensembl")
register_status(mcp, "ensembl")


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
