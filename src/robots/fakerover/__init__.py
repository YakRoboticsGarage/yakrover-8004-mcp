from core.plugin import RobotPlugin, RobotMetadata


class FakeRoverPlugin(RobotPlugin):
    def metadata(self) -> RobotMetadata:
        return RobotMetadata(
            name="Fake Rover",
            description="A simulated differential-drive rover for development and testing.",
            robot_type="differential_drive",
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

        register(mcp, FakeRoverClient())
