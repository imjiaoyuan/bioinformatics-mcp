from common.serve import register, register_status
from mcp.server.mcpserver import MCPServer

from servers.enrichr_mcp import api


mcp = MCPServer("enrichr")

register(mcp, api, "enrichr")
register_status(mcp, "enrichr")


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
