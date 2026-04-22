"""Berlin Tumbller — live-production ground-teleop robot on Base mainnet.

Distinct from the demo `tumbller` plugin: this one is registered as NPC ROBOT
with a `live_production` EAS attestation and receives real USDC payments for
executing `delivery_ground` motor-command sequences.

v1 capability surface: movement only. Temperature/humidity/visual are declared
in availability.json as unavailable until hardware is wired — bids for those
task categories decline via the availability map.

See tumbller-esp32s3/docs/MARKETPLACE_REGISTRATION_PLAN.md for the full plan.
"""

import time
from typing import Any

from core.marketplace_tools import MARKETPLACE_TOOL_NAMES
from core.plugin import BiddingTerms, RobotMetadata, RobotPlugin

from . import audit, availability, pricing, rate_limit

VALID_COMMANDS = {"forward", "backward", "left", "right", "stop"}
DEFAULT_COMMAND_GAP_SECONDS = 1.0  # pause between motor commands in a sequence


class BerlinTumbllerPlugin(RobotPlugin):
    def __init__(self) -> None:
        self._rate_limiter = rate_limit.SlidingWindowRateLimiter(
            max_requests=10,
            window_seconds=60.0,
        )
        self.client: Any = None  # set in register_tools()

    def metadata(self) -> RobotMetadata:
        return RobotMetadata(
            name="NPC ROBOT",
            description=(
                "Berlin-based ESP32-S3 two-wheeled ground robot. Accepts paid "
                "teleoperation tasks (delivery_ground category) on Base mainnet. "
                "Movement only in v1; sensor capabilities tracked in availability map."
            ),
            robot_type="differential_drive",
            url_prefix="berlin_tumbller",
            fleet_provider="yakrover",
            fleet_domain="yakrover.online/berlin",
            bidding_terms=BiddingTerms(
                min_price_cents=pricing.BASE_PRICE_CENTS,
                rate_per_minute_cents=None,  # per-command pricing, not per-minute
                currency="usdc",
                accepted_task_types=["delivery_ground"],
                max_duration_secs=120,
                max_concurrent_tasks=1,
                requires_approval=False,
            ),
        )

    def tool_names(self) -> list[str]:
        return [
            "berlin_tumbller_move",
            "berlin_tumbller_halt",
            "berlin_tumbller_is_online",
            *MARKETPLACE_TOOL_NAMES,
        ]

    def register_tools(self, mcp) -> None:
        from .client import BerlinTumbllerClient
        from .tools import register

        self.client = BerlinTumbllerClient()
        register(mcp, self.client)

    # ── Marketplace hooks ──────────────────────────────────────────────

    async def bid(self, task_spec: dict) -> dict | None:
        """Decide whether to bid on a task. Returns bid params or None to decline."""
        category = task_spec.get("task_category")
        if category != "delivery_ground":
            return None

        # Availability gate — is movement actually online right now?
        capability = availability.capability_for_task_category(category)
        if capability is None:
            return None
        available, _reason = availability.is_available(capability)
        if not available:
            # Framework collapses None → "willing_to_bid: False" with a generic reason.
            # Richer reason would require a framework change; park for now.
            return None

        # Capability requirements — we only provide movement; decline if buyer asks for more.
        reqs = task_spec.get("capability_requirements") or {}
        required_sensors = set(reqs.get("sensors_required", []))
        if required_sensors and not required_sensors.issubset(set()):  # we claim no sensors
            return None

        move_count = int(reqs.get("move_count", 1))
        price_usd = pricing.compute_price_usd(move_count)

        budget = float(task_spec.get("budget_ceiling", 0))
        if budget < price_usd:
            return None

        return {
            "price": price_usd,
            "currency": "usdc",
            "sla_commitment_seconds": max(30, move_count * 3),
            "confidence": 0.98,
            "capabilities_offered": ["movement"],
            "notes": (
                f"{move_count} motor command(s) at ${pricing.BASE_PRICE_CENTS / 100:.2f} "
                f"base + ${pricing.EXTRA_COMMAND_CENTS / 100:.2f}/extra."
            ),
        }

    async def execute(self, task_id: str, task_description: str, parameters: dict) -> dict:
        """Run the motor command sequence from `parameters['commands']`."""
        commands = parameters.get("commands") if isinstance(parameters, dict) else None
        if not isinstance(commands, list) or not commands:
            return {
                "success": False,
                "error": "parameters.commands missing or not a non-empty list",
                "partial_data": {},
            }

        invalid = [c for c in commands if c not in VALID_COMMANDS]
        if invalid:
            return {
                "success": False,
                "error": f"Invalid command(s): {invalid}. Valid: {sorted(VALID_COMMANDS)}",
                "partial_data": {},
            }

        if self.client is None:
            from .client import BerlinTumbllerClient

            self.client = BerlinTumbllerClient()

        start = time.monotonic()
        command_log: list[dict[str, Any]] = []
        completion = "completed"
        error: str | None = None

        for i, cmd in enumerate(commands):
            if not self._rate_limiter.allow():
                completion = "partial"
                error = "rate limit exceeded"
                break

            cmd_start = time.monotonic()
            try:
                await self.client.get(f"/motor/{cmd}")
            except Exception as e:
                completion = "aborted"
                error = f"motor command '{cmd}' failed: {e}"
                break
            cmd_duration_ms = int((time.monotonic() - cmd_start) * 1000)

            command_log.append(
                {
                    "command": cmd,
                    "timestamp_ms": int(time.time() * 1000),
                    "duration_ms": cmd_duration_ms,
                }
            )

            # Pause between commands so forward/backward finishes before the next one.
            if i < len(commands) - 1:
                time.sleep(DEFAULT_COMMAND_GAP_SECONDS)

        duration_s = round(time.monotonic() - start, 2)
        executed = len(command_log)

        delivery_data = {
            "task_id": task_id,
            "commands_executed": command_log,
            "duration_s": duration_s,
            "completion_status": completion,
            "robot_id": self.metadata().name,
            "summary": (
                f"Executed {executed}/{len(commands)} motor commands "
                f"in {duration_s}s ({completion})."
            ),
        }

        audit.append(
            {
                "task_id": task_id,
                "requested_commands": commands,
                "executed_count": executed,
                "completion": completion,
                "duration_s": duration_s,
                "error": error,
            }
        )

        return {
            "success": completion == "completed",
            "error": error,
            "delivery_data": delivery_data,
        }
