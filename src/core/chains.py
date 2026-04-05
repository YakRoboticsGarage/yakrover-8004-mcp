"""Chain configuration for ERC-8004 registration and discovery.

Single source of truth for supported EVM chain IDs and default RPC URLs.
Import ``get_chain`` wherever a chain ID or RPC URL is needed.
"""

CHAINS: dict[str, dict] = {
    "eth-sepolia":  {"chain_id": 11155111, "rpc": "https://ethereum-sepolia-rpc.publicnode.com"},
    "eth-mainnet":  {"chain_id": 1,        "rpc": "https://ethereum-rpc.publicnode.com"},
    "base-sepolia": {"chain_id": 84532,    "rpc": "https://sepolia.base.org"},
    "base-mainnet": {"chain_id": 8453,     "rpc": "https://mainnet.base.org"},
}

DEFAULT_CHAIN = "eth-sepolia"

CHAIN_NAMES = list(CHAINS.keys())


def get_chain(name: str | None = None) -> dict:
    """Return chain config by name.

    Falls back to the ``CHAIN`` environment variable, then ``DEFAULT_CHAIN``
    (``eth-sepolia``).

    Args:
        name: Chain name, e.g. ``"base-mainnet"``. Pass ``None`` to use the
              environment default.

    Returns:
        Dict with ``chain_id`` (int) and ``rpc`` (str) keys.

    Raises:
        KeyError: If ``name`` is not a recognised chain.
    """
    import os

    resolved = name or os.getenv("CHAIN") or DEFAULT_CHAIN
    if resolved not in CHAINS:
        raise KeyError(
            f"Unknown chain '{resolved}'. Valid options: {CHAIN_NAMES}"
        )
    return {"name": resolved, **CHAINS[resolved]}
