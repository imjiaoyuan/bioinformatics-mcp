from common.serve import register, register_status
from mcp.server.mcpserver import MCPServer

from servers.rnacentral_mcp import api


mcp = MCPServer("rnacentral")

register(mcp, api, "rnacentral")
register_status(mcp, "rnacentral")


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
