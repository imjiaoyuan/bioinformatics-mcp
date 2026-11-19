from common.serve import register, register_status
from mcp.server.mcpserver import MCPServer

from servers.wikipathways_mcp import api


mcp = MCPServer("wikipathways")

register(mcp, api, "wikipathways")
register_status(mcp, "wikipathways")


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
