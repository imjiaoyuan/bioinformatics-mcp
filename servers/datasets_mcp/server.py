from common.serve import register, register_status
from mcp.server.mcpserver import MCPServer

from servers.datasets_mcp import api


mcp = MCPServer("datasets")

register(mcp, api, "datasets")
register_status(mcp, "datasets")


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
