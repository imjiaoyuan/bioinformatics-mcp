from common.serve import register, register_status
from mcp.server.mcpserver import MCPServer

from servers.unichem_mcp import api


mcp = MCPServer("unichem")

register(mcp, api, "unichem")
register_status(mcp, "unichem")


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
