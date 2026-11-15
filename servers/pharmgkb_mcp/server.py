from common.serve import register, register_status
from mcp.server.mcpserver import MCPServer

from servers.pharmgkb_mcp import api


mcp = MCPServer("pharmgkb")

register(mcp, api, "pharmgkb")
register_status(mcp, "pharmgkb")


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
