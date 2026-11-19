from common.serve import register, register_status
from mcp.server.mcpserver import MCPServer

from servers.panelapp_mcp import api


mcp = MCPServer("panelapp")

register(mcp, api, "panelapp")
register_status(mcp, "panelapp")


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
