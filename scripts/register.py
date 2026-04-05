"""Register a robot plugin on ERC-8004.

Usage:
    uv run python scripts/register.py tumbller
    uv run python scripts/register.py tello
    uv run python scripts/register.py fakerover
    uv run python scripts/register.py tumbller --chain base-mainnet

Requires in .env: SIGNER_PVT_KEY, PINATA_JWT, NGROK_DOMAIN
Optional in .env: RPC_URL (overrides the selected chain's default public RPC)
"""

import argparse
import sys
import os

# Ensure src/ is on the path when run from repo root
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from robots import discover_plugins
from core.chains import CHAIN_NAMES, DEFAULT_CHAIN
from core.registration import register_robot

parser = argparse.ArgumentParser(description="Register a robot plugin on ERC-8004")
parser.add_argument("robot", help="Robot plugin name (e.g. tumbller, tello, fakerover)")
parser.add_argument(
    "--chain",
    choices=CHAIN_NAMES,
    default=None,
    metavar="CHAIN",
    help=f"EVM chain to register on (e.g. base-mainnet). "
         f"Defaults to CHAIN env var or {DEFAULT_CHAIN}. "
         f"Choices: {', '.join(CHAIN_NAMES)}",
)
args = parser.parse_args()

plugins = discover_plugins()
if args.robot not in plugins:
    print(f"Unknown robot: '{args.robot}'. Available: {list(plugins.keys())}")
    sys.exit(1)

plugin = plugins[args.robot]()
register_robot(plugin, chain=args.chain)
