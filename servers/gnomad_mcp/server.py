from common.serve import register, register_status
from mcp.server.mcpserver import MCPServer

from servers.gnomad_mcp import api


mcp = MCPServer("gnomad")

register(mcp, api, "gnomad")
register_status(mcp, "gnomad")


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
