"""On-chain robot discovery via ERC-8004 identity registry.

Queries the Ethereum Sepolia blockchain for robot agents registered with
the ``category=robot`` metadata key. Provides both a standalone query
function (``discover_robots``) and an MCP tool registrar
(``register_discovery_tools``) so LLMs can discover robots at runtime.
"""

import os

import requests
from agent0_sdk import SDK
from dotenv import load_dotenv
from fastmcp import FastMCP

load_dotenv()

IPFS_GATEWAY = "https://ipfs.io/ipfs/"


def _get_sdk() -> SDK:
    """Create a read-only SDK instance for on-chain queries.

    Uses RPC_URL from the environment. No signer needed — discovery is
    read-only.
    """
    return SDK(
        chainId=11155111,
        rpcUrl=os.getenv("RPC_URL", "https://ethereum-sepolia-rpc.publicnode.com"),
    )


def _fetch_ipfs_tools(sdk: SDK, agent_id_int: int) -> list:
    """Fetch MCP tools from IPFS metadata (bypasses subgraph lag)."""
    try:
        uri = sdk.identity_registry.functions.tokenURI(agent_id_int).call()
        if not uri or not uri.startswith("ipfs://"):
            return []
        cid = uri.replace("ipfs://", "")
        resp = requests.get(f"{IPFS_GATEWAY}{cid}", timeout=10)
        resp.raise_for_status()
        data = resp.json()
        for svc in data.get("services", []):
            if svc.get("name") == "MCP":
                return svc.get("mcpTools", [])
    except Exception:
        pass
    return []


def discover_robots(
    robot_type: str | None = None,
    fleet_provider: str | None = None,
) -> list[dict]:
    """Query the on-chain registry for robot agents.

    Args:
        robot_type: Filter by robot type (e.g. "differential_drive", "quadrotor").
        fleet_provider: Filter by fleet operator (e.g. "yakrover").

    Returns:
        List of dicts with agent_id, name, robot_type, fleet_provider,
        fleet_domain, and mcp_tools for each matching robot.
    """
    sdk = _get_sdk()
    results = sdk.searchAgents(hasMetadataKey="category")
    robots = []

    for agent in results:
        agent_id_str = agent.get("agentId") if isinstance(agent, dict) else agent.agentId
        agent_id_int = int(str(agent_id_str).split(":")[-1])

        # Only include agents with category=robot
        meta_category = sdk.identity_registry.functions.getMetadata(agent_id_int, "category").call()
        if meta_category != b"robot":
            continue

        rtype = sdk.identity_registry.functions.getMetadata(agent_id_int, "robot_type").call()
        provider = sdk.identity_registry.functions.getMetadata(agent_id_int, "fleet_provider").call()
        fleet = sdk.identity_registry.functions.getMetadata(agent_id_int, "fleet_domain").call()

        rtype_str = rtype.decode() if rtype else "unknown"
        provider_str = provider.decode() if provider else ""
        fleet_str = fleet.decode() if fleet else ""

        if robot_type and rtype_str != robot_type:
            continue
        if fleet_provider and provider_str != fleet_provider:
            continue

        name = agent.get("name") if isinstance(agent, dict) else agent.name
        tools = agent.get("mcpTools", []) if isinstance(agent, dict) else getattr(agent, "mcpTools", [])
        if not tools:
            tools = _fetch_ipfs_tools(sdk, agent_id_int)

        robots.append({
            "agent_id": agent_id_str,
            "name": name,
            "robot_type": rtype_str,
            "fleet_provider": provider_str,
            "fleet_domain": fleet_str,
            "mcp_tools": tools,
        })

    return robots


def register_discovery_tools(
    mcp: FastMCP,
    mounted_robots: dict[str, str] | None = None,
) -> None:
    """Register robot discovery as MCP tools for LLM consumption.

    Args:
        mcp: The FastMCP server to register tools on.
        mounted_robots: Map of plugin name → local MCP endpoint path
                        (e.g. {"tumbller": "/tumbller/mcp"}).
                        Used to enrich discovery results with local URLs.
    """
    _mounted = mounted_robots or {}

    @mcp.tool
    async def discover_robot_agents(
        robot_type: str | None = None,
        fleet_provider: str | None = None,
    ) -> dict:
        """Discover robot agents registered on the ERC-8004 identity registry.

        Searches the Ethereum Sepolia blockchain for physical robots that have
        been registered as on-chain agents. Returns their capabilities (MCP
        tools), classification (robot_type), fleet information, and — if the
        robot is running on this gateway — the local MCP endpoint URL.

        Args:
            robot_type: Filter by robot type (e.g. "differential_drive",
                        "quadrotor"). Pass None to return all types.
            fleet_provider: Filter by fleet operator (e.g. "yakrover").
                           Pass None to return all providers.

        Returns:
            A dict with a "robots" list, each entry containing:
            - agent_id: On-chain identifier
            - name: Human-readable robot name
            - robot_type: Locomotion/form-factor classification
            - fleet_provider: Organization operating the robot
            - fleet_domain: Regional fleet grouping
            - mcp_tools: List of MCP tool names the robot exposes
            - local_endpoint: MCP endpoint path on this gateway
                              (e.g. "/tumbller/mcp"), or null if not local
        """
        robots = discover_robots(robot_type=robot_type, fleet_provider=fleet_provider)

        for robot in robots:
            matched_endpoint = None
            for plugin_name, endpoint in _mounted.items():
                if plugin_name in robot.get("name", "").lower():
                    matched_endpoint = endpoint
                    break
            robot["local_endpoint"] = matched_endpoint

        return {"robots": robots, "count": len(robots)}
