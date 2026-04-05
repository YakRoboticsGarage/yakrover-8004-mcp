import logging

import stripe

from auction.models import AuctionResult

logger = logging.getLogger(__name__)


class StripePaymentHandler:
    """Stripe Checkout payment handler for robot task payments.

    Requires the ``stripe`` package (optional ``marketplace`` extra in pyproject.toml):
        uv sync --extra marketplace

    Environment variables:
        STRIPE_SECRET_KEY            — Stripe API secret key
        STRIPE_WEBHOOK_SECRET        — Webhook endpoint signing secret
        STRIPE_CONNECT_ACCOUNT_ID    — Operator's acct_... ID from Stripe Connect Express
        NGROK_DOMAIN                 — Public base URL for success/cancel redirect URLs
    """

    def __init__(self, api_key: str, webhook_secret: str, base_url: str):
        stripe.api_key = api_key
        self.webhook_secret = webhook_secret
        self.base_url = base_url.rstrip("/")

    def create_checkout_session(self, auction_id: str, auction: AuctionResult) -> str:
        """Create a Stripe Checkout session for the accepted bid.

        Uses destination charges so 88% is routed to the operator's Stripe
        Connect Express account and 12% is retained by the platform.

        Returns the Checkout URL to redirect the buyer to.
        """
        bid = auction.winning_bid
        if bid is None:
            raise ValueError(f"Auction {auction_id} has no winning bid")

        price_cents = int(bid.price * 100)
        session = stripe.checkout.Session.create(
            payment_method_types=["card"],
            line_items=[
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
            mode="payment",
            success_url=f"{self.base_url}/auction/{auction_id}/success",
            cancel_url=f"{self.base_url}/auction/{auction_id}/cancel",
            metadata={"auction_id": auction_id},
        )
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
