"""Pricing formula for the Berlin Tumbller.

Confirmed with Rafa 2026-04-22:
    $0.50 base for a single motor command, +$0.01 per additional command.

Expressed in cents to avoid float rounding.
"""

BASE_PRICE_CENTS = 50
EXTRA_COMMAND_CENTS = 1


def compute_price_cents(move_count: int) -> int:
    """Return the bid price in cents for a task with `move_count` motor commands."""
    if move_count <= 1:
        return BASE_PRICE_CENTS
    return BASE_PRICE_CENTS + EXTRA_COMMAND_CENTS * (move_count - 1)


def compute_price_usd(move_count: int) -> float:
    """Convenience wrapper returning USD as a float."""
    return compute_price_cents(move_count) / 100.0
