from common.serve import register, register_status
from mcp.server.mcpserver import MCPServer

from servers.anaconda_mcp import api


mcp = MCPServer("anaconda")

register(mcp, api, "anaconda")
register_status(mcp, "anaconda")


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
