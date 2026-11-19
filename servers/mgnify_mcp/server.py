from common.serve import register, register_status
from mcp.server.mcpserver import MCPServer

from servers.mgnify_mcp import api


mcp = MCPServer("mgnify")

register(mcp, api, "mgnify")
register_status(mcp, "mgnify")


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
