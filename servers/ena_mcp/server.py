from common.serve import register, register_status
from mcp.server.mcpserver import MCPServer

from servers.ena_mcp import api


mcp = MCPServer("ena")

register(mcp, api, "ena")
register_status(mcp, "ena")


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
