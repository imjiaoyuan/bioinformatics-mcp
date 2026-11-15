from common.serve import register, register_status
from mcp.server.mcpserver import MCPServer

from servers.singlecell_mcp import api


mcp = MCPServer("singlecell")

register(mcp, api, "singlecell")
register_status(mcp, "singlecell")


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
