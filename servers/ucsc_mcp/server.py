from common.serve import register, register_status
from mcp.server.mcpserver import MCPServer

from servers.ucsc_mcp import api


mcp = MCPServer("ucsc")

register(mcp, api, "ucsc")
register_status(mcp, "ucsc")


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
