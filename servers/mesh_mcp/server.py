from common.serve import register, register_status
from mcp.server.mcpserver import MCPServer

from servers.mesh_mcp import api


mcp = MCPServer("mesh")

register(mcp, api, "mesh")
register_status(mcp, "mesh")


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
