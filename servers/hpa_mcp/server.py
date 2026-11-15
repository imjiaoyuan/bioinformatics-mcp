from common.serve import register, register_status
from mcp.server.mcpserver import MCPServer

from servers.hpa_mcp import api


mcp = MCPServer("hpa")

register(mcp, api, "hpa")
register_status(mcp, "hpa")


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
