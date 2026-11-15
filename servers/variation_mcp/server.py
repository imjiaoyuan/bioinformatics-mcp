from common.serve import register, register_status
from mcp.server.mcpserver import MCPServer

from servers.variation_mcp import api


mcp = MCPServer("variation")

register(mcp, api, "variation")
register_status(mcp, "variation")


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
