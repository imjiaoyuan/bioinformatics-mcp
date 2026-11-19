from common.serve import register, register_status
from mcp.server.mcpserver import MCPServer

from servers.rxnorm_mcp import api


mcp = MCPServer("rxnorm")

register(mcp, api, "rxnorm")
register_status(mcp, "rxnorm")


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
