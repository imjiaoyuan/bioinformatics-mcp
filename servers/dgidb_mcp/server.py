from common.serve import register, register_status
from mcp.server.mcpserver import MCPServer

from servers.dgidb_mcp import api


mcp = MCPServer("dgidb")

register(mcp, api, "dgidb")
register_status(mcp, "dgidb")


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
