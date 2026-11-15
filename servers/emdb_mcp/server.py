from common.serve import register, register_status
from mcp.server.mcpserver import MCPServer

from servers.emdb_mcp import api


mcp = MCPServer("emdb")

register(mcp, api, "emdb")
register_status(mcp, "emdb")


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
