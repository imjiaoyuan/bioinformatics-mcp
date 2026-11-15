from common.serve import register, register_status
from mcp.server.mcpserver import MCPServer

from servers.interpro_mcp import api


mcp = MCPServer("interpro")

register(mcp, api, "interpro")
register_status(mcp, "interpro")


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
