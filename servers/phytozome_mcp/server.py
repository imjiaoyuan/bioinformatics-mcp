from common.serve import register, register_status
from mcp.server.mcpserver import MCPServer

from servers.phytozome_mcp import api


mcp = MCPServer("phytozome")

register(mcp, api, "phytozome")
register_status(mcp, "phytozome")


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
