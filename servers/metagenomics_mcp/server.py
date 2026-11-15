from common.serve import register, register_status
from mcp.server.mcpserver import MCPServer

from servers.metagenomics_mcp import api


mcp = MCPServer("metagenomics")

register(mcp, api, "metagenomics")
register_status(mcp, "metagenomics")


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
