import os

import httpx


class BerlinTumbllerClient:
    """HTTP client for the Berlin live-production Tumbller.

    Points at the public Cloudflare Tunnel URL on yakrover.online in
    production; overridable via BERLIN_TUMBLLER_URL for local dev / tests.
    No firmware auth in v1 (matches Finland Tumbller's model — see
    MARKETPLACE_REGISTRATION_PLAN.md deferred section).
    """

    def __init__(self, base_url: str | None = None):
        self.base_url = base_url or os.getenv(
            "BERLIN_TUMBLLER_URL",
            "https://berlin-tumbller-01.yakrover.online",
        )
        self.client = httpx.AsyncClient(base_url=self.base_url, timeout=5.0)

    async def get(self, path: str) -> dict:
        resp = await self.client.get(path)
        resp.raise_for_status()
        try:
            return resp.json()
        except Exception:
            return {"status": "ok", "body": resp.text}
