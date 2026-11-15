from common.serve import register, register_status
from mcp.server.mcpserver import MCPServer

from servers.clinvar_mcp import api


mcp = MCPServer("clinvar")

register(mcp, api, "clinvar")
register_status(mcp, "clinvar")


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
