from common.serve import register, register_status
from mcp.server.mcpserver import MCPServer

from servers.bvbrc_mcp import api


mcp = MCPServer("bvbrc")

register(mcp, api, "bvbrc")
register_status(mcp, "bvbrc")


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
