from common.serve import register, register_status
from mcp.server.mcpserver import MCPServer

from servers.panglao_mcp import api


mcp = MCPServer("panglao")

register(mcp, api, "panglao")
register_status(mcp, "panglao")


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
