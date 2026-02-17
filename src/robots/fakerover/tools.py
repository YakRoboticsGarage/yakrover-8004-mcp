from typing import Literal
from fastmcp import FastMCP
from .client import FakeRoverClient


def register(mcp: FastMCP, robot: FakeRoverClient) -> None:
    """Register Fake Rover MCP tools on the server."""

    @mcp.tool
    async def fakerover_move(
        direction: Literal["forward", "back", "left", "right", "stop"],
    ) -> dict:
        """Move the fake rover in a given direction.
        forward/back auto-stop after 2 seconds, left/right after 1 second,
        stop halts motors immediately."""
        return await robot.get(f"/motor/{direction}")

    @mcp.tool
    async def fakerover_is_online() -> dict:
        """Check if the fake rover simulator is running and reachable."""
        try:
            await robot.get("/info")
            return {"online": True}
        except Exception:
            return {"online": False}

    @mcp.tool
    async def fakerover_get_temperature_humidity() -> dict:
        """Read simulated temperature (C) and humidity (%) from the fake rover."""
        return await robot.get("/sensor/ht")
