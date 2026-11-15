from common.serve import register, register_status
from mcp.server.mcpserver import MCPServer

from servers.disgenet_mcp import api


mcp = MCPServer("disgenet")

register(mcp, api, "disgenet")
register_status(mcp, "disgenet")


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
