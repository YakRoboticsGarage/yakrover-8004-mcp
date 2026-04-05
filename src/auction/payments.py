import logging

import stripe

from auction.models import AuctionResult

logger = logging.getLogger(__name__)

_STRIPE_MIN_CENTS = 50  # Stripe minimum charge for USD is $0.50


class StripePaymentHandler:
    """Stripe Checkout payment handler for robot task payments.

    Requires the ``stripe`` package (optional ``marketplace`` extra in pyproject.toml):
        uv sync --extra marketplace

    When ``connect_account_id`` is provided, Checkout sessions use destination
    charges: the full amount is charged to the buyer and 88% is transferred to
    the operator's Stripe Connect Express account; 12% is retained as the
    platform fee.

    Environment variables (read by create_gateway() in server.py):
        STRIPE_SECRET_KEY            — Stripe API secret key
        STRIPE_WEBHOOK_SECRET        — Webhook endpoint signing secret
        STRIPE_CONNECT_ACCOUNT_ID    — Operator's acct_... ID (Stripe Connect Express)
        NGROK_DOMAIN                 — Public base URL for success/cancel redirects
    """

    def __init__(
        self,
        api_key: str,
        webhook_secret: str,
        base_url: str,
        connect_account_id: str | None = None,
    ):
        stripe.api_key = api_key
        self.webhook_secret = webhook_secret
        self.base_url = base_url.rstrip("/")
        self.connect_account_id = connect_account_id

    def create_checkout_session(self, auction_id: str, auction: AuctionResult) -> str:
        """Create a Stripe Checkout session for the accepted bid.

        Returns the Checkout URL to redirect the buyer to.

        Raises ValueError if the bid price is below Stripe's minimum charge
        ($0.50 USD) or if no winning bid is set on the auction.
        """
        bid = auction.winning_bid
        if bid is None:
            raise ValueError(f"Auction {auction_id} has no winning bid")

        # Use round() to avoid float rounding errors (e.g. 10.23 * 100 = 1022.9999...)
        price_cents = round(bid.price * 100)
        if price_cents < _STRIPE_MIN_CENTS:
            raise ValueError(
                f"Bid price ${bid.price:.2f} (auction {auction_id}) is below "
                f"Stripe's minimum charge of ${_STRIPE_MIN_CENTS / 100:.2f}"
            )

        session_params: dict = {
            "payment_method_types": ["card"],
            "line_items": [
                {
                    "price_data": {
                        "currency": "usd",
                        "unit_amount": price_cents,
                        "product_data": {
                            "name": f"Robot Task: {auction.task.task_description}",
                            "description": f"Executed by {bid.robot_name}",
                        },
                    },
                    "quantity": 1,
                }
            ],
            "mode": "payment",
            "success_url": f"{self.base_url}/auction/{auction_id}/success",
            "cancel_url": f"{self.base_url}/auction/{auction_id}/cancel",
            "metadata": {"auction_id": auction_id},
        }

        if self.connect_account_id:
            # Destination charge: 88% to operator, 12% platform fee
            platform_fee_cents = round(price_cents * 0.12)
            session_params["payment_intent_data"] = {
                "application_fee_amount": platform_fee_cents,
                "transfer_data": {"destination": self.connect_account_id},
            }

        session = stripe.checkout.Session.create(**session_params)
        logger.info("Stripe checkout created for auction %s: %s", auction_id, session.url)
        return session.url

    async def handle_webhook(self, payload: bytes, sig_header: str) -> str | None:
        """Verify and process a Stripe webhook event.

        Returns auction_id if checkout.session.completed, None for other event
        types. Raises ValueError on invalid signature.
        """
        try:
            event = stripe.Webhook.construct_event(payload, sig_header, self.webhook_secret)
        except Exception as exc:
            logger.warning("Stripe webhook verification failed: %s", exc)
            raise ValueError("Invalid Stripe signature") from exc

        if event["type"] == "checkout.session.completed":
            session = event["data"]["object"]
            auction_id = session.get("metadata", {}).get("auction_id")
            logger.info("Stripe payment confirmed for auction %s", auction_id)
            return auction_id

        return None
