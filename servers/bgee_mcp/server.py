from common.serve import register, register_status
from mcp.server.mcpserver import MCPServer

from servers.bgee_mcp import api


mcp = MCPServer("bgee")

register(mcp, api, "bgee")
register_status(mcp, "bgee")


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
