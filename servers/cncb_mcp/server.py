from common.serve import register, register_status
from mcp.server.mcpserver import MCPServer

from servers.cncb_mcp import api


mcp = MCPServer("cncb")

register(mcp, api, "cncb")
register_status(mcp, "cncb")


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
