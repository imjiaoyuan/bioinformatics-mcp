from common.serve import register, register_status
from mcp.server.mcpserver import MCPServer

from servers.mygene_mcp import api


mcp = MCPServer("mygene")

register(mcp, api, "mygene")
register_status(mcp, "mygene")


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
