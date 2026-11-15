from common.serve import register, register_status
from mcp.server.mcpserver import MCPServer

from servers.bioconductor_mcp import api


mcp = MCPServer("bioconductor")

register(mcp, api, "bioconductor")
register_status(mcp, "bioconductor")


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
