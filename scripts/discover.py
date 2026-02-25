"""Discover robot agents registered on ERC-8004 (Ethereum Sepolia).

Usage:
    uv run python scripts/discover.py
    uv run python scripts/discover.py --type differential_drive
    uv run python scripts/discover.py --provider yakrover
    uv run python scripts/discover.py --add-mcp
    uv run python scripts/discover.py --add-mcp --scope global

Requires in .env: RPC_URL (defaults to public Sepolia RPC if unset)
"""

import argparse
import json
import sys
import os
from pathlib import Path

# Ensure src/ is on the path when run from repo root
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from core.discovery import discover_robots


def _load_bearer_token() -> str:
    """Load MCP_BEARER_TOKEN from .env in repo root."""
    try:
        from dotenv import dotenv_values
        repo_root = Path(__file__).parent.parent
        env = dotenv_values(repo_root / ".env")
        return env.get("MCP_BEARER_TOKEN", "")
    except Exception as exc:
        print(f"  Warning: could not load MCP_BEARER_TOKEN from .env: {exc}", file=sys.stderr)
        return ""


def _server_name(robot: dict) -> str:
    """Derive an MCP server name from fleet domain + robot name.

    e.g. fleet_domain='yakrover.com/finland', name='Tumbller Self-Balancing Robot'
    → 'finland-tumbller'
    """
    domain = robot.get("fleet_domain") or ""
    domain_segment = domain.rstrip("/").rsplit("/", 1)[-1].split(".")[0]
    name = robot.get("name") or ""
    robot_slug = name.split()[0].lower() if name else robot.get("robot_type", "robot")
    if domain_segment:
        return f"{domain_segment}-{robot_slug}"
    return robot_slug


def _fleet_server_name(robot: dict) -> str:
    """Derive the fleet MCP server name from fleet domain."""
    domain = robot.get("fleet_domain") or ""
    domain_segment = domain.rstrip("/").rsplit("/", 1)[-1].split(".")[0]
    return f"{domain_segment}-fleet" if domain_segment else "fleet"


def _build_server_entry(url: str, bearer_token: str) -> dict:
    entry = {"type": "http", "url": url}
    if bearer_token:
        entry["headers"] = {"Authorization": f"Bearer {bearer_token}"}
    return entry


def _add_mcp_servers(robots: list, scope: str) -> None:
    repo_root = Path(__file__).parent.parent
    if scope == "project":
        config_path = repo_root / ".mcp.json"
    else:
        config_path = Path.home() / ".claude.json"

    if config_path.exists():
        with open(config_path) as f:
            config = json.load(f)
    else:
        config = {}

    if "mcpServers" not in config:
        config["mcpServers"] = {}

    bearer_token = _load_bearer_token()
    if not bearer_token:
        print("  Note: No MCP_BEARER_TOKEN found in .env — servers will be added without auth headers.")
    added = []
    seen_fleet_urls: set[str] = set()

    for robot in robots:
        mcp_url = robot.get("mcp_endpoint")
        if mcp_url:
            name = _server_name(robot)
            config["mcpServers"][name] = _build_server_entry(mcp_url, bearer_token)
            added.append(name)

        fleet_url = robot.get("fleet_endpoint")
        if fleet_url and fleet_url not in seen_fleet_urls:
            fleet_name = _fleet_server_name(robot)
            config["mcpServers"][fleet_name] = _build_server_entry(fleet_url, bearer_token)
            added.append(fleet_name)
            seen_fleet_urls.add(fleet_url)

    with open(config_path, "w") as f:
        json.dump(config, f, indent=2)
        f.write("\n")

    print(f"\nAdded {len(added)} MCP server(s) to {scope} config ({config_path}):")
    for name in added:
        print(f"  {name}")


parser = argparse.ArgumentParser(description="Discover robot agents on-chain")
parser.add_argument("--type", dest="robot_type", help="Filter by robot type (e.g. differential_drive, quadrotor)")
parser.add_argument("--provider", dest="fleet_provider", help="Filter by fleet provider (e.g. yakrover)")
parser.add_argument("--add-mcp", action="store_true", help="Add discovered robots as MCP servers in Claude config")
parser.add_argument("--scope", choices=["project", "global"], default="project",
                    help="MCP config scope: 'project' (.mcp.json) or 'global' (~/.claude.json) (default: project)")
args = parser.parse_args()

print("Querying ERC-8004 registry on Ethereum Sepolia...\n")

robots = discover_robots(robot_type=args.robot_type, fleet_provider=args.fleet_provider)

if not robots:
    print("No robot agents found.")
    sys.exit(0)

print(f"Found {len(robots)} robot agent(s):\n")

for robot in robots:
    print(f"  {robot['name']}")
    print(f"    Agent ID:       {robot['agent_id']}")
    print(f"    Robot type:     {robot['robot_type']}")
    print(f"    Fleet provider: {robot['fleet_provider'] or '(none)'}")
    print(f"    Fleet domain:   {robot['fleet_domain'] or '(none)'}")
    print(f"    MCP endpoint:   {robot.get('mcp_endpoint') or '(none)'}")
    print(f"    Fleet endpoint: {robot.get('fleet_endpoint') or '(none)'}")
    print(f"    MCP tools:      {robot['mcp_tools'] or '(none)'}")
    print()

# Also dump as JSON for programmatic use
print("---\nJSON output:")
print(json.dumps(robots, indent=2))

if args.add_mcp:
    _add_mcp_servers(robots, args.scope)
