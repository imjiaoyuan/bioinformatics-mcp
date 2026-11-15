from common.serve import register, register_status
from mcp.server.mcpserver import MCPServer

from servers.alphafold_mcp import api


mcp = MCPServer("alphafold")

register(mcp, api, "alphafold")
register_status(mcp, "alphafold")


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
