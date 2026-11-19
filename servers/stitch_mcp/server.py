from common.serve import register, register_status
from mcp.server.mcpserver import MCPServer

from servers.stitch_mcp import api


mcp = MCPServer("stitch")

register(mcp, api, "stitch")
register_status(mcp, "stitch")


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
