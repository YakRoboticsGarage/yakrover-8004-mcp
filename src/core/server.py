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


def create_gateway(plugins: dict[str, RobotPlugin]) -> FastAPI:
    """Create a FastAPI gateway that sub-mounts each robot's MCP server.

    Each robot gets its own isolated FastMCP instance mounted at /{name}/.
    All served on a single port behind one ngrok tunnel.

    FastMCP v3 requires each MCP app's lifespan to be started for its
    StreamableHTTPSessionManager task group. We compose all lifespans
    into the gateway's lifespan.
    """
    mcp_apps = {}
    for name, plugin in plugins.items():
        mcp = create_robot_server(plugin)
        mcp_apps[name] = mcp.http_app()

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
