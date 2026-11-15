from common.serve import register, register_status
from mcp.server.mcpserver import MCPServer

from servers.encode_mcp import api


mcp = MCPServer("encode")

register(mcp, api, "encode")
register_status(mcp, "encode")


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
