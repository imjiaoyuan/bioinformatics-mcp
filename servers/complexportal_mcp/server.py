from common.serve import register, register_status
from mcp.server.mcpserver import MCPServer

from servers.complexportal_mcp import api


mcp = MCPServer("complexportal")

register(mcp, api, "complexportal")
register_status(mcp, "complexportal")


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
