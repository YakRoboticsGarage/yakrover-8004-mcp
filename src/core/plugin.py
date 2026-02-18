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
