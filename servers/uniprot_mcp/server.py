from common.serve import register, register_status
from mcp.server.mcpserver import MCPServer

from servers.uniprot_mcp import api


mcp = MCPServer("uniprot")

register(mcp, api, "uniprot")
register_status(mcp, "uniprot")


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
