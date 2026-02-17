from fastmcp import FastMCP
from .client import TemplateClient


def register(mcp: FastMCP, robot: TemplateClient) -> None:
    """Register your robot's MCP tools on the server."""

    @mcp.tool
    async def myrobot_is_online() -> dict:
        """Check if the robot is online and reachable."""
        try:
            await robot.get("/info")
            return {"online": True}
        except Exception:
            return {"online": False}
