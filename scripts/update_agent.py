"""Update an existing on-chain robot agent.

Loads the agent by ID, refreshes MCP endpoint, tool list, and metadata
from the plugin, re-uploads to IPFS, and submits the update transaction.

Usage:
    uv run python scripts/update_agent.py tumbller 11155111:989
    uv run python scripts/update_agent.py tello 11155111:990

Requires in .env: RPC_URL, SIGNER_PVT_KEY, PINATA_JWT, NGROK_DOMAIN
"""

import argparse
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from robots import discover_plugins
from core.registration import update_robot

parser = argparse.ArgumentParser(description="Update an existing on-chain robot agent")
parser.add_argument("robot", help="Robot plugin name (e.g. tumbller, tello, fakerover)")
parser.add_argument("agent_id", help="On-chain agent ID (e.g. 11155111:989)")
args = parser.parse_args()

plugins = discover_plugins()
if args.robot not in plugins:
    print(f"Unknown robot: '{args.robot}'. Available: {list(plugins.keys())}")
    sys.exit(1)

plugin = plugins[args.robot]()
update_robot(plugin, args.agent_id)
