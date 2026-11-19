from common.serve import register, register_status
from mcp.server.mcpserver import MCPServer

from servers.metabolights_mcp import api


mcp = MCPServer("metabolights")

register(mcp, api, "metabolights")
register_status(mcp, "metabolights")


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
