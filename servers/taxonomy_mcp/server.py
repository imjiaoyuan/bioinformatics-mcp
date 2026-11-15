from common.serve import register, register_status
from mcp.server.mcpserver import MCPServer

from servers.taxonomy_mcp import api


mcp = MCPServer("taxonomy")

register(mcp, api, "taxonomy")
register_status(mcp, "taxonomy")


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
