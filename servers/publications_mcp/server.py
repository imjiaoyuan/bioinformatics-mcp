from common.serve import register, register_status
from mcp.server.mcpserver import MCPServer

from servers.publications_mcp import api


mcp = MCPServer("publications")

register(mcp, api, "publications")
register_status(mcp, "publications")


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
