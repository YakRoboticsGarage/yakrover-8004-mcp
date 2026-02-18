from core.plugin import RobotPlugin, RobotMetadata


class TelloPlugin(RobotPlugin):
    def metadata(self) -> RobotMetadata:
        return RobotMetadata(
            name="DJI Tello Drone",
            description="A DJI Tello quadrotor drone controllable via MCP.",
            robot_type="quadrotor",
            fleet_provider="yakrover",
            fleet_domain="yakrover.com/finland",
        )

    def tool_names(self) -> list[str]:
        return [
            "tello_takeoff",
            "tello_land",
            "tello_move",
            "tello_rotate",
            "tello_flip",
            "tello_get_status",
            "tello_get_attitude",
            "tello_get_drone_info",
            "tello_is_online",
        ]

    def register_tools(self, mcp):
        from .client import TelloClient
        from .tools import register

        register(mcp, TelloClient())
