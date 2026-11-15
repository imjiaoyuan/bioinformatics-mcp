from common.serve import register, register_status
from mcp.server.mcpserver import MCPServer

from servers.hgnc_mcp import api


mcp = MCPServer("hgnc")

register(mcp, api, "hgnc")
register_status(mcp, "hgnc")


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
