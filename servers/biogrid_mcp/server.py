from common.serve import register, register_status
from mcp.server.mcpserver import MCPServer

from servers.biogrid_mcp import api


mcp = MCPServer("biogrid")

register(mcp, api, "biogrid")
register_status(mcp, "biogrid")


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
