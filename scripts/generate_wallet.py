"""Generate or display the Ethereum wallet for ERC-8004 registration.

Usage:
    uv run python scripts/generate_wallet.py          # Show existing wallet from .env
    uv run python scripts/generate_wallet.py --new    # Generate new wallet and save to .env
"""

import argparse
import sys
import os

# Ensure src/ is on the path when run from repo root
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from core.wallet import get_existing_wallet, generate_and_save

parser = argparse.ArgumentParser(description="Manage the Ethereum wallet for ERC-8004 registration")
parser.add_argument("--new", action="store_true", help="Generate a new wallet and save to .env")
args = parser.parse_args()

if args.new:
    generate_and_save()
else:
    account = get_existing_wallet()
    if account:
        print("=== Existing Wallet (from .env) ===")
        print(f"Address: {account.address}")
    else:
        print("No wallet found in .env. Run with --new to generate one:")
        print("  uv run python scripts/generate_wallet.py --new")
        sys.exit(1)
