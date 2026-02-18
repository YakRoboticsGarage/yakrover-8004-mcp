"""Fix on-chain metadata for an existing robot agent.

Directly sets metadata keys on-chain without IPFS re-upload.
Useful for correcting metadata after registration or migrating
from old key names (e.g. agent_type → category).

Usage:
    uv run python scripts/fix_metadata.py tumbller 989
    uv run python scripts/fix_metadata.py tello 990

Requires in .env: RPC_URL, SIGNER_PVT_KEY
"""

import argparse
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from robots import discover_plugins
from core.registration import fix_metadata

parser = argparse.ArgumentParser(description="Fix on-chain metadata for a robot agent")
parser.add_argument("robot", help="Robot plugin name (e.g. tumbller, tello, fakerover)")
parser.add_argument("agent_id", type=int, help="Numeric agent ID on the identity registry (e.g. 989)")
args = parser.parse_args()

plugins = discover_plugins()
if args.robot not in plugins:
    print(f"Unknown robot: '{args.robot}'. Available: {list(plugins.keys())}")
    sys.exit(1)

plugin = plugins[args.robot]()
fix_metadata(plugin, args.agent_id)
