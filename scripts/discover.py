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
import re
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


def _build_claude_entry(url: str, bearer_token: str) -> dict:
    entry = {"type": "http", "url": url}
    if bearer_token:
        entry["headers"] = {"Authorization": f"Bearer {bearer_token}"}
    return entry


def _build_opencode_entry(url: str, bearer_token: str) -> dict:
    entry: dict = {"type": "remote", "url": url, "enabled": True}
    if bearer_token:
        entry["headers"] = {"Authorization": f"Bearer {bearer_token}"}
    return entry


def _load_jsonc(config_path: Path) -> dict:
    """Load a JSON or JSONC file, stripping single-line // comments."""
    if not config_path.exists():
        return {}
    text = config_path.read_text()
    text = re.sub(r"(?m)^\s*//[^\n]*$", "", text)
    try:
        return json.loads(text)
    except json.JSONDecodeError as e:
        print(f"  Warning: could not parse {config_path}: {e}", file=sys.stderr)
        return {}


def _write_json(config_path: Path, config: dict) -> None:
    with open(config_path, "w") as f:
        json.dump(config, f, indent=2)
        f.write("\n")


def _add_mcp_servers(robots: list, scope: str) -> None:
    repo_root = Path(__file__).parent.parent
    bearer_token = _load_bearer_token()
    if not bearer_token:
        print("  Note: No MCP_BEARER_TOKEN found in .env — servers will be added without auth headers.")

    # --- Claude config ---
    if scope == "project":
        claude_path = repo_root / ".mcp.json"
    else:
        claude_path = Path.home() / ".claude.json"

    claude_config = _load_jsonc(claude_path) if claude_path.exists() else {}
    if "mcpServers" not in claude_config:
        claude_config["mcpServers"] = {}

    # --- OpenCode config ---
    if scope == "project":
        opencode_path = repo_root / "opencode.jsonc"
    else:
        opencode_path = Path.home() / ".config" / "opencode" / "opencode.json"
        opencode_path.parent.mkdir(parents=True, exist_ok=True)

    opencode_config = _load_jsonc(opencode_path)
    if "$schema" not in opencode_config:
        opencode_config["$schema"] = "https://opencode.ai/config.json"
    if "mcp" not in opencode_config:
        opencode_config["mcp"] = {}

    added = []
    seen_fleet_urls: set[str] = set()

    for robot in robots:
        mcp_url = robot.get("mcp_endpoint")
        if mcp_url:
            name = _server_name(robot)
            claude_config["mcpServers"][name] = _build_claude_entry(mcp_url, bearer_token)
            opencode_config["mcp"][name] = _build_opencode_entry(mcp_url, bearer_token)
            added.append(name)

        fleet_url = robot.get("fleet_endpoint")
        if fleet_url and fleet_url not in seen_fleet_urls:
            fleet_name = _fleet_server_name(robot)
            claude_config["mcpServers"][fleet_name] = _build_claude_entry(fleet_url, bearer_token)
            opencode_config["mcp"][fleet_name] = _build_opencode_entry(fleet_url, bearer_token)
            added.append(fleet_name)
            seen_fleet_urls.add(fleet_url)

    _write_json(claude_path, claude_config)
    _write_json(opencode_path, opencode_config)

    print(f"\nAdded {len(added)} MCP server(s) to {scope} config:")
    print(f"  Claude:   {claude_path}")
    print(f"  OpenCode: {opencode_path}")
    for name in added:
        print(f"  {name}")


parser = argparse.ArgumentParser(description="Discover robot agents on-chain")
parser.add_argument("--type", dest="robot_type", help="Filter by robot type (e.g. differential_drive, quadrotor)")
parser.add_argument("--provider", dest="fleet_provider", help="Filter by fleet provider (e.g. yakrover)")
parser.add_argument("--add-mcp", action="store_true", help="Add discovered robots as MCP servers in Claude and OpenCode configs")
parser.add_argument("--scope", choices=["project", "global"], default="project",
                    help="MCP config scope: 'project' (.mcp.json + opencode.jsonc) or 'global' (~/.claude.json + ~/.config/opencode/opencode.json) (default: project)")
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
