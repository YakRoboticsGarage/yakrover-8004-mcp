import logging

from fastapi import HTTPException, Request

logger = logging.getLogger(__name__)


def make_stripe_webhook_route(payment_handler, engine):
    """Return a FastAPI route handler for POST /stripe/webhook.

    Mounted in create_gateway() when STRIPE_SECRET_KEY and
    STRIPE_WEBHOOK_SECRET are set. Verifies the Stripe signature, then calls
    engine.on_payment_confirmed() which:
      - marks the auction status as "paid"
      - auto-executes the task if the winning robot has requires_approval=False
    """

    async def stripe_webhook(request: Request):
        payload = await request.body()
        sig_header = request.headers.get("stripe-signature", "")

        try:
            auction_id = await payment_handler.handle_webhook(payload, sig_header)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc))

        if auction_id:
            try:
                await engine.on_payment_confirmed(auction_id)
            except Exception as exc:
                logger.error(
                    "Failed to process confirmed payment for auction %s: %s",
                    auction_id,
                    exc,
                )

        return {"received": True}

    return stripe_webhook
