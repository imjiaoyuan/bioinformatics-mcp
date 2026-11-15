from common.serve import register, register_status
from mcp.server.mcpserver import MCPServer

from servers.clinicaltrials_mcp import api


mcp = MCPServer("clinicaltrials")

register(mcp, api, "clinicaltrials")
register_status(mcp, "clinicaltrials")


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
