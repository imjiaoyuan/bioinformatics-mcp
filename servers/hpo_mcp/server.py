from common.serve import register, register_status
from mcp.server.mcpserver import MCPServer

from servers.hpo_mcp import api


mcp = MCPServer("hpo")

register(mcp, api, "hpo")
register_status(mcp, "hpo")


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
