import time

from core.marketplace_tools import MARKETPLACE_TOOL_NAMES
from core.plugin import BiddingTerms, RobotPlugin, RobotMetadata


class FakeRoverPlugin(RobotPlugin):
    def metadata(self) -> RobotMetadata:
        return RobotMetadata(
            name="FakeRover-Finland-01",
            description="A simulated differential-drive rover for development and testing.",
            robot_type="differential_drive",
            url_prefix="fakerover",
            fleet_provider="yakrover",
            fleet_domain="yakrover.com/dev",
            bidding_terms=BiddingTerms(
                min_price_cents=50,
                rate_per_minute_cents=10,
                currency="usd",
                accepted_task_types=["sensor_reading"],
                max_duration_secs=180,
                max_concurrent_tasks=1,
                requires_approval=True,
            ),
        )

    def tool_names(self) -> list[str]:
        return [
            "fakerover_move",
            "fakerover_is_online",
            "fakerover_get_temperature_humidity",
            *MARKETPLACE_TOOL_NAMES,
        ]

    def register_tools(self, mcp):
        from .client import FakeRoverClient
        from .tools import register

        self.client = FakeRoverClient()
        register(mcp, self.client)

    async def bid(self, task_spec: dict) -> dict | None:
        """Generate a bid for env_sensing tasks after verifying liveness and sensors."""
        from .client import FakeRoverClient

        # Category filter — only bid on sensor/environmental tasks
        if task_spec.get("task_category") not in ("env_sensing", "sensor_reading"):
            return None

        # Capability check
        reqs = task_spec.get("capability_requirements") or {}
        required_sensors = set(reqs.get("sensors_required", []))
        if required_sensors and not required_sensors.issubset({"temperature", "humidity"}):
            return None  # buyer needs sensors we don't have

        # Budget check
        terms = self.metadata().bidding_terms
        min_price = terms.min_price_cents / 100
        if task_spec.get("budget_ceiling", 0) < min_price:
            return None

        # Liveness check
        client = getattr(self, "client", None) or FakeRoverClient()
        try:
            await client.get("/info")
            await client.get("/sensor/ht")
        except Exception:
            return None  # simulator offline or sensor failed

        return {
            "price": min_price,
            "currency": "usd",
            "sla_commitment_seconds": 30,
            "confidence": 0.95,
            "capabilities_offered": ["temperature", "humidity"],
            "notes": "AHT20 sensor (simulated), accuracy ±0.3°C / ±2% RH.",
        }

    async def execute(self, task_id: str, task_description: str, parameters: dict) -> dict:
        """Read sensor data and return delivery_data."""
        from .client import FakeRoverClient

        client = getattr(self, "client", None) or FakeRoverClient()
        start = time.monotonic()
        try:
            sensor_data = await client.get("/sensor/ht")
        except Exception as e:
            return {"success": False, "error": f"Sensor read failed: {e}", "partial_data": {}}

        duration = round(time.monotonic() - start, 2)
        temp = sensor_data.get("temperature")
        hum = sensor_data.get("humidity")
        meta = self.metadata()

        return {
            "success": True,
            "delivery_data": {
                "readings": [
                    {"type": "temperature", "value": temp, "unit": "celsius"},
                    {"type": "humidity", "value": hum, "unit": "percent_rh"},
                ],
                "summary": f"Temperature: {temp}°C, Humidity: {hum}%",
                "robot_id": "simulator",
                "robot_name": meta.name,
                "duration_seconds": duration,
            },
        }
