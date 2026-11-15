from common.serve import register, register_status
from mcp.server.mcpserver import MCPServer

from servers.mondo_mcp import api


mcp = MCPServer("mondo")

register(mcp, api, "mondo")
register_status(mcp, "mondo")


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
