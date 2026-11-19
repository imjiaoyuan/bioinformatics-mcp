from common.serve import register, register_status
from mcp.server.mcpserver import MCPServer

from servers.ols_mcp import api


mcp = MCPServer("ols")

register(mcp, api, "ols")
register_status(mcp, "ols")


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
