from common.serve import register, register_status
from mcp.server.mcpserver import MCPServer

from servers.cbioportal_mcp import api


mcp = MCPServer("cbioportal")

register(mcp, api, "cbioportal")
register_status(mcp, "cbioportal")


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
