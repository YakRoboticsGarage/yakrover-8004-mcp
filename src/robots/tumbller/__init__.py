import time

from core.marketplace_tools import MARKETPLACE_TOOL_NAMES
from core.plugin import BiddingTerms, RobotPlugin, RobotMetadata


class TumbllerPlugin(RobotPlugin):
    def metadata(self) -> RobotMetadata:
        return RobotMetadata(
            name="Tumbller Self-Balancing Robot",
            description="A physical ESP32-S3 two-wheeled robot controllable via MCP.",
            robot_type="differential_drive",
            url_prefix="tumbller",
            fleet_provider="yakrover",
            fleet_domain="yakrover.com/finland",
            bidding_terms=BiddingTerms(
                min_price_cents=50,
                rate_per_minute_cents=10,
                currency="usd",
                accepted_task_types=["sensor_reading"],
                max_duration_secs=60,
                max_concurrent_tasks=1,
                requires_approval=True,
            ),
        )

    def tool_names(self) -> list[str]:
        return [
            "tumbller_move",
            "tumbller_is_online",
            "tumbller_get_temperature_humidity",
            *MARKETPLACE_TOOL_NAMES,
        ]

    def register_tools(self, mcp):
        from .client import TumbllerClient
        from .tools import register

        self.client = TumbllerClient()
        register(mcp, self.client)

    async def bid(self, task_spec: dict) -> dict | None:
        """Generate a bid for env_sensing tasks after a liveness check."""
        # Category filter — Tumbller handles sensor/environmental tasks only
        if task_spec.get("task_category") not in ("env_sensing", "sensor_reading"):
            return None

        # Capability check — verify buyer's required sensors are a subset of ours
        reqs = task_spec.get("capability_requirements") or {}
        required_sensors = set(reqs.get("sensors_required", []))
        if required_sensors and not required_sensors.issubset({"temperature", "humidity"}):
            return None

        # Budget check
        terms = self.metadata().bidding_terms
        min_price = terms.min_price_cents / 100
        if task_spec.get("budget_ceiling", 0) < min_price:
            return None

        # Liveness check — reuse stored client from register_tools if available
        client = getattr(self, "client", None)
        if client is None:
            from .client import TumbllerClient
            client = TumbllerClient()
        try:
            await client.get("/info")
        except Exception:
            return None  # robot offline

        return {
            "price": min_price,
            "currency": "usd",
            "sla_commitment_seconds": 30,
            "confidence": 0.95,
            "capabilities_offered": ["temperature", "humidity"],
            "notes": "SHT3x sensor, accuracy ±0.3°C / ±2% RH.",
        }

    async def execute(self, task_id: str, task_description: str, parameters: dict) -> dict:
        """Read temperature and humidity and return delivery_data."""
        client = getattr(self, "client", None)
        if client is None:
            from .client import TumbllerClient
            client = TumbllerClient()

        start = time.monotonic()
        try:
            sensor_data = await client.get("/sensor/ht")
        except Exception as e:
            return {"success": False, "error": f"Sensor read failed: {e}", "partial_data": {}}

        duration = round(time.monotonic() - start, 2)
        temp = sensor_data.get("temperature")
        hum = sensor_data.get("humidity")

        return {
            "success": True,
            "delivery_data": {
                "readings": [
                    {"type": "temperature", "value": temp, "unit": "celsius"},
                    {"type": "humidity", "value": hum, "unit": "percent_rh"},
                ],
                "summary": f"Temperature: {temp}°C, Humidity: {hum}%",
                "robot_id": "989",  # ERC-8004 agent ID on eth-sepolia
                "robot_name": self.metadata().name,
                "duration_seconds": duration,
            },
        }
