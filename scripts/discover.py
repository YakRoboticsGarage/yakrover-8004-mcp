"""Discover robot agents registered on ERC-8004 (Ethereum Sepolia).

Usage:
    uv run python scripts/discover.py
    uv run python scripts/discover.py --type differential_drive
    uv run python scripts/discover.py --provider yakrover

Requires in .env: RPC_URL (defaults to public Sepolia RPC if unset)
"""

import argparse
import json
import sys
import os

# Ensure src/ is on the path when run from repo root
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from core.discovery import discover_robots

parser = argparse.ArgumentParser(description="Discover robot agents on-chain")
parser.add_argument("--type", dest="robot_type", help="Filter by robot type (e.g. differential_drive, quadrotor)")
parser.add_argument("--provider", dest="fleet_provider", help="Filter by fleet provider (e.g. yakrover)")
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
    print(f"    MCP tools:      {robot['mcp_tools'] or '(none)'}")
    print()

# Also dump as JSON for programmatic use
print("---\nJSON output:")
print(json.dumps(robots, indent=2))
