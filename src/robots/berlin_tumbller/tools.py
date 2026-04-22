from typing import Literal

from fastmcp import FastMCP

from .client import BerlinTumbllerClient


def register(mcp: FastMCP, robot: BerlinTumbllerClient) -> None:
    """Register Berlin Tumbller MCP tools.

    Movement-only in v1 — no temperature/humidity tool. Sensor capabilities
    are declared in the availability map and surfaced through bid() as
    "not available" until the hardware is wired.
    """

    @mcp.tool
    async def berlin_tumbller_move(
        direction: Literal["forward", "backward", "left", "right", "stop"],
    ) -> dict:
        """Move the Berlin Tumbller in a given direction.

        forward/backward auto-stop after 2 seconds, left/right after 1 second,
        stop halts motors immediately.
        """
        return await robot.get(f"/motor/{direction}")

    @mcp.tool
    async def berlin_tumbller_halt() -> dict:
        """Emergency stop — halts motors and cancels any pending movement."""
        return await robot.get("/motor/stop")

    @mcp.tool
    async def berlin_tumbller_is_online() -> dict:
        """Check if the Berlin Tumbller is reachable over the Cloudflare Tunnel."""
        try:
            await robot.get("/info")
            return {"online": True}
        except Exception:
            return {"online": False}
