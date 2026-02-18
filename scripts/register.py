"""Register a robot plugin on ERC-8004 (Ethereum Sepolia).

Usage:
    uv run python scripts/register.py tumbller
    uv run python scripts/register.py tello
    uv run python scripts/register.py fakerover

Requires in .env: RPC_URL, SIGNER_PVT_KEY, PINATA_JWT, NGROK_DOMAIN
"""

import argparse
import sys
import os

# Ensure src/ is on the path when run from repo root
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from robots import discover_plugins
from core.registration import register_robot

parser = argparse.ArgumentParser(description="Register a robot plugin on ERC-8004")
parser.add_argument("robot", help="Robot plugin name (e.g. tumbller, tello, fakerover)")
args = parser.parse_args()

plugins = discover_plugins()
if args.robot not in plugins:
    print(f"Unknown robot: '{args.robot}'. Available: {list(plugins.keys())}")
    sys.exit(1)

plugin = plugins[args.robot]()
register_robot(plugin)
