from common.serve import register, register_status
from mcp.server.mcpserver import MCPServer

from servers.depmap_mcp import api


mcp = MCPServer("depmap")

register(mcp, api, "depmap")
register_status(mcp, "depmap")


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
