from common.serve import register, register_status
from mcp.server.mcpserver import MCPServer

from servers.vep_mcp import api


mcp = MCPServer("vep")

register(mcp, api, "vep")
register_status(mcp, "vep")


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
