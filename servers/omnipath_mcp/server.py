from common.serve import register, register_status
from mcp.server.mcpserver import MCPServer

from servers.omnipath_mcp import api


mcp = MCPServer("omnipath")

register(mcp, api, "omnipath")
register_status(mcp, "omnipath")


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
