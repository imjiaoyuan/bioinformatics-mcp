from common.serve import register, register_status
from mcp.server.mcpserver import MCPServer

from servers.intact_mcp import api


mcp = MCPServer("intact")

register(mcp, api, "intact")
register_status(mcp, "intact")


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
