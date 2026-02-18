"""Start an ngrok tunnel to the MCP gateway using a static free domain."""

import os

from pyngrok import ngrok


def start_tunnel(port: int = 8000) -> str:
    """Open an ngrok tunnel and return the public HTTPS URL.

    Requires NGROK_AUTHTOKEN and NGROK_DOMAIN in the environment.
    """
    auth_token = os.getenv("NGROK_AUTHTOKEN")
    domain = os.getenv("NGROK_DOMAIN")

    if not auth_token:
        raise RuntimeError("NGROK_AUTHTOKEN not set in .env")
    if not domain:
        raise RuntimeError(
            "NGROK_DOMAIN not set in .env (claim at https://dashboard.ngrok.com/domains)"
        )

    ngrok.set_auth_token(auth_token)
    ngrok.connect(
        addr=str(port),
        proto="http",
        hostname=domain,
    )
    return f"https://{domain}"
