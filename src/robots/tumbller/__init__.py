from core.plugin import RobotPlugin, RobotMetadata


class TumbllerPlugin(RobotPlugin):
    def metadata(self) -> RobotMetadata:
        return RobotMetadata(
            name="Tumbller Self-Balancing Robot",
            description="A physical ESP32-S3 two-wheeled robot controllable via MCP.",
            robot_type="differential_drive",
            fleet_provider="yakrover",
            fleet_domain="yakrover.com/finland",
        )

    def tool_names(self) -> list[str]:
        return [
            "tumbller_move",
            "tumbller_is_online",
            "tumbller_get_temperature_humidity",
        ]

    def register_tools(self, mcp):
        from .client import TumbllerClient
        from .tools import register

        register(mcp, TumbllerClient())
