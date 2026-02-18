import os
from contextlib import asynccontextmanager

from dotenv import load_dotenv
from fastapi import FastAPI
from fastmcp import FastMCP

from core.plugin import RobotPlugin

load_dotenv()


def _make_auth():
    """Create shared auth provider if MCP_BEARER_TOKEN is set."""
    bearer_token = os.getenv("MCP_BEARER_TOKEN")
    if not bearer_token:
        return None
    from fastmcp.server.auth.providers.jwt import StaticTokenVerifier

    return StaticTokenVerifier(
        tokens={bearer_token: {"client_id": "mcp-client", "scopes": []}}
    )


def create_robot_server(plugin: RobotPlugin) -> FastMCP:
    """Create an isolated FastMCP server for a single robot plugin."""
    meta = plugin.metadata()
    auth = _make_auth()

    mcp = FastMCP(
        name=meta.name,
        instructions=f"Control and monitor: {meta.name}",
        auth=auth,
    )
    plugin.register_tools(mcp)
    return mcp


def create_fleet_server(mounted_robots: dict[str, str] | None = None) -> FastMCP:
    """Create the fleet orchestrator MCP server (discovery + lifecycle).

    Args:
        mounted_robots: Map of plugin name → endpoint path, passed to
                        discovery tools so results include local URLs.
    """
    auth = _make_auth()

    mcp = FastMCP(
        name="Robot Fleet Orchestrator",
        instructions="Discover robots on-chain and manage the fleet.",
        auth=auth,
    )

    from core.discovery import register_discovery_tools

    register_discovery_tools(mcp, mounted_robots=mounted_robots)

    return mcp


def create_gateway(plugins: dict[str, RobotPlugin]) -> FastAPI:
    """Create a FastAPI gateway that sub-mounts each robot's MCP server.

    Each robot gets its own isolated FastMCP instance mounted at /{name}/.
    The fleet orchestrator is mounted at /fleet/.
    All served on a single port behind one ngrok tunnel.

    FastMCP v3 requires each MCP app's lifespan to be started for its
    StreamableHTTPSessionManager task group. We compose all lifespans
    into the gateway's lifespan.
    """
    mcp_apps = {}
    mounted_robots: dict[str, str] = {}
    for name, plugin in plugins.items():
        mcp = create_robot_server(plugin)
        mcp_apps[name] = mcp.http_app()
        mounted_robots[name] = f"/{name}/mcp"

    # Fleet orchestrator (discovery tools)
    fleet_mcp = create_fleet_server(mounted_robots=mounted_robots)
    mcp_apps["fleet"] = fleet_mcp.http_app()

    @asynccontextmanager
    async def lifespan(app):
        # Start all MCP app lifespans (initializes their task groups)
        async with _compose_lifespans(mcp_apps.values()):
            yield

    app = FastAPI(title="Robot Fleet Gateway", lifespan=lifespan)

    for name, mcp_app in mcp_apps.items():
        app.mount(f"/{name}", mcp_app)

    @app.get("/")
    async def index():
        return {
            "service": "Robot Fleet Gateway",
            "robots": {
                name: {
                    "mcp_endpoint": f"/{name}/mcp",
                    "tools": plugin.tool_names(),
                }
                for name, plugin in plugins.items()
            },
            "fleet_endpoint": "/fleet/mcp",
        }

    return app


@asynccontextmanager
async def _compose_lifespans(apps):
    """Recursively enter the lifespan of each ASGI app."""
    apps = list(apps)
    if not apps:
        yield
        return

    first, *rest = apps
    async with first.lifespan(first):
        async with _compose_lifespans(rest):
            yield
