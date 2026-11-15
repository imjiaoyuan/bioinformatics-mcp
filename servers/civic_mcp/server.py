from common.serve import register, register_status
from mcp.server.mcpserver import MCPServer

from servers.civic_mcp import api


mcp = MCPServer("civic")

register(mcp, api, "civic")
register_status(mcp, "civic")


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
