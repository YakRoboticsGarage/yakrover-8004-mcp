from typing import Literal

from fastmcp import FastMCP

from .client import TumbllerClient


def register(mcp: FastMCP, robot: TumbllerClient) -> None:
    """Register Tumbller MCP tools on the server."""

    @mcp.tool
    async def tumbller_move(
        direction: Literal["forward", "back", "left", "right", "stop"],
    ) -> dict:
        """Move the Tumbller robot in a given direction.
        forward/back auto-stop after 2 seconds, left/right after 1 second,
        stop halts motors immediately."""
        return await robot.get(f"/motor/{direction}")

    @mcp.tool
    async def tumbller_is_online() -> dict:
        """Check if the Tumbller robot is online and reachable."""
        try:
            await robot.get("/info")
            return {"online": True}
        except Exception:
            return {"online": False}

    @mcp.tool
    async def tumbller_get_temperature_humidity() -> dict:
        """Read temperature (C) and humidity (%) from the Tumbller's SHT3x sensor."""
        return await robot.get("/sensor/ht")
