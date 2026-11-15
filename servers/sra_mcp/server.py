from common.serve import register, register_status
from mcp.server.mcpserver import MCPServer

from servers.sra_mcp import api


mcp = MCPServer("sra")

register(mcp, api, "sra")
register_status(mcp, "sra")


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
