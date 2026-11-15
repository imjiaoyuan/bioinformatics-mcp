from common.serve import register, register_status
from mcp.server.mcpserver import MCPServer

from servers.pdb_mcp import api


mcp = MCPServer("pdb")

register(mcp, api, "pdb")
register_status(mcp, "pdb")


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
