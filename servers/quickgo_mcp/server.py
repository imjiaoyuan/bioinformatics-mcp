from common.serve import register, register_status
from mcp.server.mcpserver import MCPServer

from servers.quickgo_mcp import api


mcp = MCPServer("quickgo")

register(mcp, api, "quickgo")
register_status(mcp, "quickgo")


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
