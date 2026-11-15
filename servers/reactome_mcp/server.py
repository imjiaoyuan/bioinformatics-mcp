from common.serve import register, register_status
from mcp.server.mcpserver import MCPServer

from servers.reactome_mcp import api


mcp = MCPServer("reactome")

register(mcp, api, "reactome")
register_status(mcp, "reactome")


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
