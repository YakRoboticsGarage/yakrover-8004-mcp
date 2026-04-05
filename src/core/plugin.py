from abc import ABC, abstractmethod
from dataclasses import dataclass
from fastmcp import FastMCP


@dataclass
class RobotMetadata:
    """On-chain classification for ERC-8004 registration."""

    name: str
    description: str
    robot_type: str
    url_prefix: str = ""        # URL path segment (e.g. "tumbller" → /tumbller/mcp)
    fleet_provider: str = ""
    fleet_domain: str = ""
    image: str = ""


class RobotPlugin(ABC):
    """Base class for all robot plugins.

    A plugin is responsible for:
    1. Declaring its metadata (name, type, fleet info)
    2. Registering its MCP tools on a FastMCP server instance
    3. Providing its tool names for on-chain registration
    """

    @abstractmethod
    def metadata(self) -> RobotMetadata:
        """Return the robot's on-chain metadata."""
        ...

    @abstractmethod
    def register_tools(self, mcp: FastMCP) -> None:
        """Register this robot's MCP tools on the shared server."""
        ...

    @abstractmethod
    def tool_names(self) -> list[str]:
        """Return the list of MCP tool names this plugin registers.

        Must match the function names passed to @mcp.tool exactly.
        """
        ...

    async def bid(self, task_spec: dict) -> dict | None:
        """Generate a bid for a task. Override in auction-participating plugins.

        Returns bid parameters dict or None to decline.
        Default: returns None (backward-compatible opt-out).
        """
        return None

    async def execute(self, task_id: str, task_description: str, parameters: dict) -> dict:
        """Execute an accepted task. Override in auction-participating plugins.

        Returns a delivery_data dict with at minimum {"success": bool}.
        Default: returns a not-implemented failure so the engine marks the
        auction as 'failed' rather than crashing.
        """
        return {"success": False, "error": "execute() not implemented for this plugin."}
