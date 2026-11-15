from common.serve import register, register_status
from mcp.server.mcpserver import MCPServer

from servers.gprofiler_mcp import api


mcp = MCPServer("gprofiler")

register(mcp, api, "gprofiler")
register_status(mcp, "gprofiler")


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
