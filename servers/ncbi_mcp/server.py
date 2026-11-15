from common.serve import register, register_status
from mcp.server.mcpserver import MCPServer

from servers.ncbi_mcp import api


mcp = MCPServer("ncbi")

register(mcp, api, "ncbi")
register_status(mcp, "ncbi")


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
