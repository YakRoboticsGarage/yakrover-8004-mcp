"""Fix on-chain metadata for an existing robot agent.

Directly sets metadata keys on-chain without IPFS re-upload.
Useful for correcting metadata after registration or migrating
from old key names (e.g. agent_type → category).

Note: bidding terms live in the IPFS agent card — use update_agent.py to
change them, not this script.

Usage:
    uv run python scripts/fix_metadata.py tumbller 989
    uv run python scripts/fix_metadata.py tello 990
    uv run python scripts/fix_metadata.py tumbller 42 --chain base-mainnet

Requires in .env: RPC_URL, SIGNER_PVT_KEY
"""

import argparse
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from robots import discover_plugins
from core.chains import CHAIN_NAMES, DEFAULT_CHAIN
from core.registration import fix_metadata

parser = argparse.ArgumentParser(description="Fix on-chain metadata for a robot agent")
parser.add_argument("robot", help="Robot plugin name (e.g. tumbller, tello, fakerover)")
parser.add_argument("agent_id", type=int, help="Numeric agent ID on the identity registry (e.g. 989)")
parser.add_argument(
    "--chain",
    choices=CHAIN_NAMES,
    default=None,
    metavar="CHAIN",
    help=f"EVM chain the agent lives on (e.g. base-mainnet). "
         f"Defaults to CHAIN env var or {DEFAULT_CHAIN}. "
         f"Choices: {', '.join(CHAIN_NAMES)}",
)
args = parser.parse_args()

plugins = discover_plugins()
if args.robot not in plugins:
    print(f"Unknown robot: '{args.robot}'. Available: {list(plugins.keys())}")
    sys.exit(1)

plugin = plugins[args.robot]()
fix_metadata(plugin, args.agent_id, chain=args.chain)
