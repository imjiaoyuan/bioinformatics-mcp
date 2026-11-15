from common.serve import register, register_status
from mcp.server.mcpserver import MCPServer

from servers.expressionatlas_mcp import api


mcp = MCPServer("expressionatlas")

register(mcp, api, "expressionatlas")
register_status(mcp, "expressionatlas")


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
