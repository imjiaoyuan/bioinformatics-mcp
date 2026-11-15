from common.serve import register, register_status
from mcp.server.mcpserver import MCPServer

from servers.pubchem_mcp import api


mcp = MCPServer("pubchem")

register(mcp, api, "pubchem")
register_status(mcp, "pubchem")


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
