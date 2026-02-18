"""Ethereum wallet generation and display.

Usage via scripts/generate_wallet.py:
    uv run python scripts/generate_wallet.py          # Show existing wallet from .env
    uv run python scripts/generate_wallet.py --new    # Generate new wallet and save to .env
"""

import os
import re

from dotenv import load_dotenv
from web3 import Web3


def _env_path() -> str:
    """Return path to .env file at repo root."""
    return os.path.join(os.path.dirname(__file__), "..", "..", ".env")


def _update_env(key: str, value: str) -> None:
    """Update or append a key=value line in the .env file."""
    path = os.path.abspath(_env_path())
    try:
        with open(path, "r") as f:
            content = f.read()
    except FileNotFoundError:
        content = ""

    if re.search(rf"^{key}=.*$", content, re.MULTILINE):
        content = re.sub(rf"^{key}=.*$", f"{key}={value}", content, flags=re.MULTILINE)
    else:
        content += f"\n{key}={value}\n"

    with open(path, "w") as f:
        f.write(content)


def get_existing_wallet():
    """Return the Web3 account from SIGNER_PVT_KEY in .env, or None."""
    load_dotenv(_env_path())
    key = os.getenv("SIGNER_PVT_KEY", "").strip()
    if not key:
        return None
    return Web3().eth.account.from_key(key)


def generate_and_save():
    """Generate a new Ethereum wallet, save to .env, and print it."""
    account = Web3().eth.account.create()
    _update_env("SIGNER_PVT_KEY", account.key.hex())
    _update_env("WALLET_ADDRESS", account.address)

    print("=== New Ethereum Wallet ===")
    print(f"Address: {account.address}")
    print("\nSaved to .env")
    print("\nNext step: fund with Sepolia ETH:")
    print("  https://www.alchemy.com/faucets/ethereum-sepolia")
    return account
