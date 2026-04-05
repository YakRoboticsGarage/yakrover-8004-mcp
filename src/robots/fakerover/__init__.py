from core.plugin import RobotPlugin, RobotMetadata


class FakeRoverPlugin(RobotPlugin):
    def metadata(self) -> RobotMetadata:
        return RobotMetadata(
            name="FakeRover-Finland-01",
            description="A simulated differential-drive rover for development and testing.",
            robot_type="differential_drive",
            url_prefix="fakerover",
            fleet_provider="yakrover",
            fleet_domain="yakrover.com/dev",
        )

    def tool_names(self) -> list[str]:
        return [
            "fakerover_move",
            "fakerover_is_online",
            "fakerover_get_temperature_humidity",
        ]

    def register_tools(self, mcp):
        from .client import FakeRoverClient
        from .tools import register

        self.client = FakeRoverClient()
        register(mcp, self.client)

    async def bid(self, task_spec: dict) -> dict | None:
        """Generate a bid after querying the simulator for liveness and capability match.

        Returns a bid dict if the simulator is online, sensors are working, and the
        fakerover's capabilities satisfy the task requirements. Returns None otherwise.
        """
        from .client import FakeRoverClient

        # Use existing client if register_tools was called, otherwise create one
        client = getattr(self, "client", None) or FakeRoverClient()

        # 1. Query simulator for current state
        try:
            info = await client.get("/info")
        except Exception:
            return None  # Simulator offline

        # 2. Verify sensor is working
        try:
            sensor_data = await client.get("/sensor/ht")
        except Exception:
            return None  # Sensor read failed

        # 3. Check capability requirements
        hard = task_spec.get("capability_requirements", {}).get("hard", {})
        required_sensors = set(hard.get("sensors_required", []))
        available_sensors = {"temperature", "humidity"}

        if not required_sensors.issubset(available_sensors):
            return None  # Cannot satisfy sensor requirements

        # 4. Build and return the bid
        return {
            "robot_id": self.metadata().name,
            "price": "0.50",
            "sla_commitment_seconds": 180,
            "ai_confidence": 0.95,
            "capability_metadata": {
                "sensors": [
                    {"type": "temperature", "model": "AHT20", "accuracy_celsius": 0.3},
                    {"type": "humidity", "model": "AHT20", "accuracy_rh_pct": 2.0},
                ],
                "mobility_type": "ground_wheeled",
                "indoor_capable": True,
                "location": "fakerover_simulator",
                "battery_percent": 100,  # simulator always 100%
            },
            "reputation_metadata": {
                "completion_rate": 0.95,
                "tasks_completed": 0,
                "on_time_rate": 1.0,
                "rejection_rate": 0.0,
                "rolling_window_days": 30,
            },
        }
