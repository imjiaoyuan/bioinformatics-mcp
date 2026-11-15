from common.serve import register, register_status
from mcp.server.mcpserver import MCPServer

from servers.chembl_mcp import api


mcp = MCPServer("chembl")

register(mcp, api, "chembl")
register_status(mcp, "chembl")


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
