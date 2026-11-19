from common.serve import register, register_status
from mcp.server.mcpserver import MCPServer

from servers.opentree_mcp import api


mcp = MCPServer("opentree")

register(mcp, api, "opentree")
register_status(mcp, "opentree")


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
