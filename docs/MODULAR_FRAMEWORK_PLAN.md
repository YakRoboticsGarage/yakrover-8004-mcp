# Modular Robot MCP Framework — Design Plan

## 1. Problem Statement

Two robot repos (`tumbller-8004-mcp` and `tello-8004-mcp`) share ~80% identical code:

| File | Shared? | Robot-specific parts |
|------|---------|---------------------|
| `tunnel.py` | 100% identical | — |
| `discover_robot_agent.py` | 100% identical | — |
| `generate_wallet.py` | 100% identical | — |
| `register_agent.py` | Same structure | name, description, tool list, metadata values |
| `update_agent.py` | Same structure | agent ID, tool list |
| `fix_metadata.py` | Same structure | agent ID, metadata values |
| `server.py` | Same scaffolding | tool definitions, client class |
| `*_client.py` | — | 100% robot-specific |

Adding a third robot (e.g., a robotic arm) would mean copy-pasting the entire repo again and changing the same small set of values. This doesn't scale.

**Goals:**
1. One generic repo that works for any robot with minimal per-robot glue code
2. A plugin system where each robot type is a self-contained module declaring its affordances
3. The `discover_robot_agent` script exposed as an MCP tool so LLMs can discover and reason about available robots at runtime

---

## 2. Proposed Repository Structure

```
yakrover-8004-mcp/
├── pyproject.toml                     # Core deps + optional extras per robot
├── .env.example
├── README.md
├── src/
│   ├── core/                          # Shared infrastructure (never changes per robot)
│   │   ├── __init__.py
│   │   ├── server.py                  # FastAPI gateway + ASGI sub-mount orchestration
│   │   ├── tunnel.py                  # ngrok tunnel (unchanged)
│   │   ├── discovery.py               # Robot discovery (from discover_robot_agent.py)
│   │   ├── registration.py            # Generic ERC-8004 register/update/fix
│   │   ├── wallet.py                  # Wallet generation (unchanged)
│   │   └── plugin.py                  # Plugin base class + registry
│   │
│   └── robots/                        # One sub-package per robot type
│       ├── __init__.py                # Robot registry auto-discovery
│       ├── tumbller/
│       │   ├── __init__.py            # Plugin registration entry point
│       │   ├── client.py              # TumbllerClient (unchanged)
│       │   └── tools.py               # MCP tool definitions (from server.py)
│       │
│       ├── tello/
│       │   ├── __init__.py
│       │   ├── client.py              # TelloClient (unchanged)
│       │   └── tools.py               # MCP tool definitions (from server.py)
│       │
│       ├── fakerover/                  # Software-only dev/test rover
│       │   ├── __init__.py            # FakeRoverPlugin
│       │   ├── client.py              # FakeRoverClient (httpx, same as Tumbller)
│       │   ├── tools.py              # MCP tool definitions
│       │   └── simulator.py          # Standalone HTTP server emulating Tumbller endpoints
│       │
│       └── _template/                 # Copyable template for new robots
│           ├── __init__.py
│           ├── client.py
│           └── tools.py
│
├── scripts/                           # CLI entry points
│   ├── serve.py                       # Start MCP server for one or more robots
│   ├── register.py                    # Register a robot on-chain
│   ├── discover.py                    # CLI wrapper for discovery
│   └── generate_wallet.py            # Wallet generation CLI
│
└── docs/
    ├── ADDING_A_ROBOT.md             # Step-by-step guide for contributors
    └── ARCHITECTURE.md
```

---

## 3. Plugin System Design

### 3.1. Plugin Base Class

Each robot plugin implements a single class that declares everything the framework needs:

```python
# src/core/plugin.py

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from fastmcp import FastMCP


@dataclass
class RobotMetadata:
    """On-chain classification for ERC-8004 registration."""
    name: str                          # e.g. "Tumbller Self-Balancing Robot"
    description: str                   # Human-readable description
    robot_type: str                    # e.g. "differential_drive", "quadrotor"
    fleet_provider: str = ""           # e.g. "yakrover"
    fleet_domain: str = ""             # e.g. "yakrover.com/finland"
    image: str = ""                    # Optional image URL


class RobotPlugin(ABC):
    """Base class for all robot plugins.

    A plugin is responsible for:
    1. Declaring its metadata (name, type, fleet info)
    2. Registering its MCP tools on a FastMCP server instance
    3. Providing its tool names for on-chain registration
    """

    @abstractmethod
    def metadata(self) -> RobotMetadata:
        """Return the robot's on-chain metadata."""
        ...

    @abstractmethod
    def register_tools(self, mcp: FastMCP) -> None:
        """Register this robot's MCP tools on the shared server.

        Use @mcp.tool to register each tool function.
        The plugin owns its client lifecycle internally.
        """
        ...

    @abstractmethod
    def tool_names(self) -> list[str]:
        """Return the list of MCP tool names this plugin registers.

        Must match the function names passed to @mcp.tool exactly.
        Used for on-chain registration in the mcpTools field.
        """
        ...
```

### 3.2. Example Plugin Implementation (Tumbller)

```python
# src/robots/tumbller/__init__.py

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
        return ["tumbller_move", "tumbller_is_online", "tumbller_get_temperature_humidity"]

    def register_tools(self, mcp):
        from .client import TumbllerClient
        from .tools import register
        register(mcp, TumbllerClient())
```

```python
# src/robots/tumbller/tools.py

from typing import Literal
from fastmcp import FastMCP
from .client import TumbllerClient


def register(mcp: FastMCP, robot: TumbllerClient) -> None:
    """Register Tumbller MCP tools on the server."""

    @mcp.tool
    async def tumbller_move(direction: Literal["forward", "back", "left", "right", "stop"]) -> dict:
        """Move the Tumbller robot in a given direction."""
        return await robot.get(f"/motor/{direction}")

    @mcp.tool
    async def tumbller_is_online() -> dict:
        """Check if the Tumbller robot is online and reachable."""
        try:
            await robot.get("/info")
            return {"online": True}
        except Exception:
            return {"online": False}

    @mcp.tool
    async def tumbller_get_temperature_humidity() -> dict:
        """Read temperature (C) and humidity (%) from the Tumbller's SHT3x sensor."""
        return await robot.get("/sensor/ht")
```

### 3.3. Tool Naming Convention

When multiple robots are loaded into a single MCP server, tool names must be globally unique. Convention:

```
{robot_type_short}_{action}
```

Examples:
- `tumbller_move`, `tumbller_is_online`
- `tello_takeoff`, `tello_move`, `tello_get_status`

If only one robot is loaded (single-robot mode), the prefix can be omitted for backward compatibility.

### 3.4. Plugin Auto-Discovery

```python
# src/robots/__init__.py

import importlib
import pkgutil
from core.plugin import RobotPlugin

def discover_plugins() -> dict[str, type[RobotPlugin]]:
    """Scan src/robots/ for packages that export a RobotPlugin subclass."""
    plugins = {}
    package = importlib.import_module("robots")
    for importer, modname, ispkg in pkgutil.iter_modules(package.__path__):
        if not ispkg or modname.startswith("_"):
            continue
        mod = importlib.import_module(f"robots.{modname}")
        for attr in dir(mod):
            obj = getattr(mod, attr)
            if isinstance(obj, type) and issubclass(obj, RobotPlugin) and obj is not RobotPlugin:
                plugins[modname] = obj
    return plugins
```

This means adding a new robot is: create a package under `src/robots/`, implement the three methods, done.

---

## 4. Generic MCP Server (ASGI Sub-Mount Architecture)

The framework uses **ASGI sub-mounting** to give each robot its own isolated MCP server instance, all served behind a single port and a single ngrok tunnel. A lightweight FastAPI gateway mounts each robot's FastMCP app at a dedicated path prefix.

```
Single ngrok tunnel → https://your-domain.ngrok.app
    /fleet/mcp      → Fleet orchestrator (discovery + lifecycle)
    /tumbller/mcp   → Tumbller MCP server (tumbller tools only)
    /tello/mcp      → Tello MCP server (tello tools only)
```

**Why ASGI sub-mounts over alternatives:**

| Approach | Isolation | Complexity | ngrok tunnels | Lifecycle control |
|----------|-----------|------------|---------------|-------------------|
| Single MCP server (all tools merged) | None | Low | 1 | All-or-nothing |
| Separate processes + reverse proxy | Full process isolation | High | 1 (with proxy) | Per-robot |
| **ASGI sub-mounts (chosen)** | **Per-robot MCP instances** | **Low-Medium** | **1** | **Per-robot** |

### 4.1. Server Bootstrap

```python
# src/core/server.py

import os
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
    """
    app = FastAPI(title="Robot Fleet Gateway")

    # Mount each robot plugin at its own path
    robot_servers: dict[str, FastMCP] = {}
    mounted_robots: dict[str, str] = {}
    for name, plugin in plugins.items():
        mcp = create_robot_server(plugin)
        robot_servers[name] = mcp
        endpoint = f"/{name}/mcp"
        mounted_robots[name] = endpoint
        app.mount(f"/{name}", mcp.get_asgi_app())

    # Mount fleet orchestrator (discovery + lifecycle tools)
    # Pass mounted_robots so discovery results include local endpoint URLs
    fleet_mcp = create_fleet_server(mounted_robots=mounted_robots)
    app.mount("/fleet", fleet_mcp.get_asgi_app())

    # Health / info endpoint
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
```

### 4.2. Serve Script

```python
# scripts/serve.py

"""
Usage:
    # Serve all installed robot plugins (each at its own sub-path)
    uv run python scripts/serve.py --ngrok

    # Serve only specific robots
    uv run python scripts/serve.py --robots tumbller tello --ngrok

    # Custom port
    uv run python scripts/serve.py --robots tello --port 8001

Endpoints created:
    /fleet/mcp          — Fleet orchestrator (discovery, lifecycle)
    /tumbller/mcp       — Tumbller robot MCP server
    /tello/mcp          — Tello drone MCP server
    /                   — Gateway info (lists all mounted robots)
"""

import argparse
import uvicorn
from robots import discover_plugins
from core.server import create_gateway

parser = argparse.ArgumentParser()
parser.add_argument("--robots", nargs="*", help="Robot plugins to load (default: all)")
parser.add_argument("--port", type=int, default=8000)
parser.add_argument("--ngrok", action="store_true")
args = parser.parse_args()

# Discover and filter plugins
all_plugins = discover_plugins()
if args.robots:
    selected = {k: v for k, v in all_plugins.items() if k in args.robots}
else:
    selected = all_plugins

plugins = {name: cls() for name, cls in selected.items()}
app = create_gateway(plugins)

if args.ngrok:
    from core.tunnel import start_tunnel
    start_tunnel(args.port)

try:
    uvicorn.run(app, host="0.0.0.0", port=args.port)
except KeyboardInterrupt:
    print("\nShutting down.")
```

### 4.3. Modes of Operation

| Mode | Command | Endpoints created |
|------|---------|-------------------|
| **Fleet mode** | `serve.py` | `/fleet/mcp` + `/{robot}/mcp` for every discovered plugin |
| **Single robot** | `serve.py --robots tello` | `/fleet/mcp` + `/tello/mcp` |
| **Multi-select** | `serve.py --robots tumbller tello` | `/fleet/mcp` + `/tumbller/mcp` + `/tello/mcp` |

### 4.4. LLM Connection

Each robot is a separate MCP endpoint. An LLM connects to individual robots as needed:

```jsonc
// Example MCP client config (e.g. in Claude Desktop)
{
  "mcpServers": {
    "fleet": {
      "url": "https://your-domain.ngrok.app/fleet/mcp"
    },
    "tumbller": {
      "url": "https://your-domain.ngrok.app/tumbller/mcp"
    },
    "tello": {
      "url": "https://your-domain.ngrok.app/tello/mcp"
    }
  }
}
```

Or the LLM can first connect to `/fleet/mcp`, call `discover_robot_agents()` to find available robots, and then connect to specific robot endpoints dynamically.

---

## 5. Discovery as an MCP Tool

The key addition: `discover_robot_agent.py` becomes an MCP tool that any LLM can call at runtime.

### 5.1. Discovery Tool Implementation

```python
# src/core/discovery.py

from agent0_sdk import SDK
from fastmcp import FastMCP
import requests

IPFS_GATEWAY = "https://ipfs.io/ipfs/"


def _get_sdk() -> SDK:
    return SDK(
        chainId=11155111,
        rpcUrl="https://ethereum-sepolia-rpc.publicnode.com",
    )


def _fetch_ipfs_tools(sdk: SDK, agent_id_int: int) -> list:
    """Fetch MCP tools from IPFS (bypasses subgraph lag)."""
    try:
        uri = sdk.identity_registry.functions.tokenURI(agent_id_int).call()
        if not uri or not uri.startswith("ipfs://"):
            return []
        cid = uri.replace("ipfs://", "")
        resp = requests.get(f"{IPFS_GATEWAY}{cid}", timeout=10)
        resp.raise_for_status()
        data = resp.json()
        for svc in data.get("services", []):
            if svc.get("name") == "MCP":
                return svc.get("mcpTools", [])
    except Exception:
        pass
    return []


def discover_robots(robot_type: str | None = None, fleet_provider: str | None = None) -> list[dict]:
    """Query on-chain registry for robot agents, with optional filters."""
    sdk = _get_sdk()
    results = sdk.searchAgents(hasMetadataKey="category")
    robots = []

    for agent in results:
        agent_id_str = agent.get("agentId") if isinstance(agent, dict) else agent.agentId
        agent_id_int = int(str(agent_id_str).split(":")[-1])

        meta = sdk.identity_registry.functions.getMetadata(agent_id_int, "category").call()
        if meta != b"robot":
            continue

        rtype = sdk.identity_registry.functions.getMetadata(agent_id_int, "robot_type").call()
        provider = sdk.identity_registry.functions.getMetadata(agent_id_int, "fleet_provider").call()
        fleet = sdk.identity_registry.functions.getMetadata(agent_id_int, "fleet_domain").call()

        rtype_str = rtype.decode() if rtype else "unknown"
        provider_str = provider.decode() if provider else ""
        fleet_str = fleet.decode() if fleet else ""

        # Apply optional filters
        if robot_type and rtype_str != robot_type:
            continue
        if fleet_provider and provider_str != fleet_provider:
            continue

        name = agent.get("name") if isinstance(agent, dict) else agent.name
        tools = agent.get("mcpTools", []) if isinstance(agent, dict) else agent.mcpTools
        if not tools:
            tools = _fetch_ipfs_tools(sdk, agent_id_int)

        robots.append({
            "agent_id": agent_id_str,
            "name": name,
            "robot_type": rtype_str,
            "fleet_provider": provider_str,
            "fleet_domain": fleet_str,
            "mcp_tools": tools,
        })

    return robots


def register_discovery_tools(mcp: FastMCP, mounted_robots: dict[str, str] | None = None) -> None:
    """Register robot discovery as MCP tools for LLM consumption.

    Args:
        mcp: The FastMCP server to register tools on.
        mounted_robots: Map of robot plugin name → local MCP endpoint path
                        (e.g. {"tumbller": "/tumbller/mcp", "tello": "/tello/mcp"}).
                        Used to enrich discovery results with local connection URLs.
    """
    _mounted = mounted_robots or {}

    @mcp.tool
    async def discover_robot_agents(
        robot_type: str | None = None,
        fleet_provider: str | None = None,
    ) -> dict:
        """Discover robot agents registered on the ERC-8004 identity registry.

        Searches the Ethereum Sepolia blockchain for physical robots that have
        been registered as on-chain agents. Returns their capabilities (MCP tools),
        classification (robot_type), fleet information, and — if the robot is
        running on this gateway — the local MCP endpoint URL to connect to.

        Args:
            robot_type: Filter by robot type (e.g. "differential_drive", "quadrotor").
                        Pass None to return all robot types.
            fleet_provider: Filter by fleet operator (e.g. "yakrover").
                           Pass None to return all providers.

        Returns:
            A dict with a "robots" list, each entry containing:
            - agent_id: On-chain identifier
            - name: Human-readable robot name
            - robot_type: Locomotion/form-factor classification
            - fleet_provider: Organization operating the robot
            - fleet_domain: Regional fleet grouping
            - mcp_tools: List of MCP tool names the robot exposes
            - local_endpoint: MCP endpoint path on this gateway (e.g. "/tumbller/mcp"),
                              or null if the robot is not mounted locally
        """
        robots = discover_robots(robot_type=robot_type, fleet_provider=fleet_provider)

        # Enrich with local endpoint info for robots mounted on this gateway
        for robot in robots:
            # Match on-chain robot name to locally mounted plugin name
            matched_endpoint = None
            for plugin_name, endpoint in _mounted.items():
                if plugin_name in robot.get("name", "").lower():
                    matched_endpoint = endpoint
                    break
            robot["local_endpoint"] = matched_endpoint

        return {"robots": robots, "count": len(robots)}
```

### 5.2. What This Enables for LLMs

An LLM connected to the fleet MCP server can:

1. **Discover** — call `discover_robot_agents()` to find all available robots on-chain
2. **Filter** — call `discover_robot_agents(robot_type="quadrotor")` to find only drones
3. **Inspect** — read the `mcp_tools` field to understand each robot's affordances
4. **Connect** — read the `local_endpoint` field to get the MCP URL for robots running on this gateway
5. **Act** — connect to the robot's endpoint and call its tools (e.g. `tello_takeoff`, `tumbller_move`)

### 5.3. Example Discovery Response

```json
{
  "robots": [
    {
      "agent_id": "eip155:11155111:42",
      "name": "Tumbller Self-Balancing Robot",
      "robot_type": "differential_drive",
      "fleet_provider": "yakrover",
      "fleet_domain": "yakrover.com/finland",
      "mcp_tools": ["tumbller_move", "tumbller_is_online", "tumbller_get_temperature_humidity"],
      "local_endpoint": "/tumbller/mcp"
    },
    {
      "agent_id": "eip155:11155111:43",
      "name": "Tello Drone",
      "robot_type": "quadrotor",
      "fleet_provider": "yakrover",
      "fleet_domain": "yakrover.com/finland",
      "mcp_tools": ["tello_takeoff", "tello_land", "tello_move", "tello_get_status"],
      "local_endpoint": "/tello/mcp"
    },
    {
      "agent_id": "eip155:11155111:99",
      "name": "Remote Arm Robot",
      "robot_type": "articulated_arm",
      "fleet_provider": "other-org",
      "fleet_domain": "other-org.com/lab",
      "mcp_tools": ["arm_move_joint", "arm_go_home"],
      "local_endpoint": null
    }
  ],
  "count": 3
}
```

Note: the third robot has `local_endpoint: null` because it's registered on-chain but not mounted on this gateway. The LLM knows it exists but can't control it from here.

---

## 6. Generic Registration

### 6.1. Registration Script

```python
# scripts/register.py

"""
Usage:
    uv run python scripts/register.py tumbller
    uv run python scripts/register.py tello
"""

import argparse
from robots import discover_plugins
from core.registration import register_robot

parser = argparse.ArgumentParser()
parser.add_argument("robot", help="Robot plugin name (e.g. tumbller, tello)")
args = parser.parse_args()

plugins = discover_plugins()
if args.robot not in plugins:
    print(f"Unknown robot: {args.robot}. Available: {list(plugins.keys())}")
    exit(1)

plugin = plugins[args.robot]()
register_robot(plugin)
```

### 6.2. Generic Registration Logic

```python
# src/core/registration.py

import os
from dotenv import load_dotenv
from agent0_sdk import SDK
from agent0_sdk.core.models import EndpointType
from core.plugin import RobotPlugin

load_dotenv()


def register_robot(plugin: RobotPlugin) -> None:
    """Register a robot plugin on ERC-8004."""
    meta = plugin.metadata()

    sdk = SDK(
        chainId=11155111,
        rpcUrl=os.environ["RPC_URL"],
        signer=os.environ["SIGNER_PVT_KEY"],
        ipfs="pinata",
        pinataJwt=os.environ["PINATA_JWT"],
    )

    agent = sdk.createAgent(
        name=meta.name,
        description=meta.description,
        image=meta.image,
    )

    ngrok_domain = os.environ["NGROK_DOMAIN"]
    agent.setMCP(f"https://{ngrok_domain}/mcp", auto_fetch=False)

    mcp_ep = next(ep for ep in agent.registration_file.endpoints if ep.type == EndpointType.MCP)
    mcp_ep.meta["mcpTools"] = plugin.tool_names()

    agent.setTrust(reputation=True)
    agent.setActive(True)
    agent.setX402Support(False)

    agent.setMetadata({
        "category": "robot",
        "robot_type": meta.robot_type,
        "fleet_provider": meta.fleet_provider,
        "fleet_domain": meta.fleet_domain,
    })

    print("Submitting registration transaction...")
    tx_handle = agent.registerIPFS()
    print(f"Transaction submitted: {tx_handle.tx_hash}")

    print("Waiting for transaction to be mined...")
    mined = tx_handle.wait_mined(timeout=120)
    reg_file = mined.result

    print(f"\nAgent registered on Ethereum Sepolia!")
    print(f"Agent ID: {reg_file.agentId}")
    print(f"Agent URI: {reg_file.agentURI}")
```

---

## 7. How to Add a New Robot

Adding a new robot (e.g., a robotic arm) requires creating **one directory with three files**:

### Step 1: Create the plugin package

```
src/robots/arm/
├── __init__.py
├── client.py
└── tools.py
```

### Step 2: Implement the client

`client.py` — handles communication with the physical robot (HTTP, UDP, serial, ROS, etc.). This is entirely robot-specific.

### Step 3: Implement the plugin

`__init__.py`:

```python
from core.plugin import RobotPlugin, RobotMetadata

class ArmPlugin(RobotPlugin):
    def metadata(self):
        return RobotMetadata(
            name="6-DOF Robotic Arm",
            description="A 6-axis robotic arm controllable via MCP.",
            robot_type="articulated_arm",
            fleet_provider="yakrover",
            fleet_domain="yakrover.com/finland",
        )

    def tool_names(self):
        return ["arm_move_joint", "arm_go_home", "arm_get_position", "arm_is_online"]

    def register_tools(self, mcp):
        from .client import ArmClient
        from .tools import register
        register(mcp, ArmClient())
```

### Step 4: Implement the tools

`tools.py`:

```python
def register(mcp, arm):
    @mcp.tool
    async def arm_move_joint(joint: int, angle: float) -> dict:
        """Move a joint to a target angle."""
        return await arm.move_joint(joint, angle)

    @mcp.tool
    async def arm_go_home() -> dict:
        """Move all joints to home position."""
        return await arm.go_home()

    # ... more tools
```

### Step 5: Add robot-specific dependencies (if any)

In `pyproject.toml`, add an optional dependency group:

```toml
[project.optional-dependencies]
tumbller = ["httpx>=0.28.1"]
tello = ["djitellopy>=2.5.0"]
fakerover = ["httpx>=0.28.1"]
arm = ["pyserial>=3.5"]
```

Install with: `uv sync --extra arm`

### That's it.

The framework auto-discovers the plugin, the server loads its tools, and `discover_robot_agents` returns it to any LLM. No framework code changes needed.

---

## 8. Dependency Management

### 8.1. pyproject.toml Structure

```toml
[project]
name = "yakrover-8004-mcp"
version = "0.1.0"
description = "Modular MCP framework for multi-robot fleet control and discovery"
requires-python = ">=3.13"

# Core dependencies (always installed)
dependencies = [
    "agent0-sdk>=1.5.2",
    "fastmcp>=2.14.5",
    "fastapi>=0.115.0",
    "uvicorn>=0.34.0",
    "pyngrok>=7.5.0",
    "python-dotenv>=1.2.1",
    "web3>=7.14.1",
    "requests>=2.31.0",
]

# Robot-specific dependencies (install only what you need)
[project.optional-dependencies]
tumbller = ["httpx>=0.28.1"]
tello = ["djitellopy>=2.5.0"]
fakerover = ["httpx>=0.28.1"]                   # same client lib as tumbller
all = ["httpx>=0.28.1", "djitellopy>=2.5.0"]   # everything
```

### 8.2. Install Commands

```bash
# Core only (discovery + registration, no robot control)
uv sync

# With specific robot support
uv sync --extra tumbller
uv sync --extra tello

# Everything
uv sync --extra all
```

---

## 9. Architecture Diagram

```
┌─────────────────────────────────────────────────────────────────┐
│                        LLM / AI Agent                           │
│  (Claude, GPT, etc. connected via MCP)                          │
└───────┬───────────────────┬───────────────────┬─────────────────┘
        │                   │                   │
        │ /fleet/mcp        │ /tumbller/mcp     │ /tello/mcp
        │                   │                   │
┌───────▼───────────────────▼───────────────────▼─────────────────┐
│                                                                  │
│              ngrok tunnel (single URL, single port)              │
│              https://your-domain.ngrok.app                       │
│                                                                  │
├──────────────────────────────────────────────────────────────────┤
│                                                                  │
│              FastAPI Gateway (ASGI sub-mounts)                   │
│              port 8000                                           │
│                                                                  │
│  ┌─────────────────┐  ┌──────────────────┐  ┌───────────────┐  │
│  │ /fleet/mcp       │  │ /tumbller/mcp    │  │ /tello/mcp    │  │
│  │ Fleet MCP Server │  │ Tumbller MCP     │  │ Tello MCP     │  │
│  │                  │  │ Server           │  │ Server        │  │
│  │ discover_robot   │  │                  │  │               │  │
│  │ _agents()        │  │ tumbller_move    │  │ tello_takeoff │  │
│  │                  │  │ tumbller_is      │  │ tello_land    │  │
│  │ Queries ERC-8004 │  │ _online()        │  │ tello_move    │  │
│  │ on Sepolia       │  │ tumbller_get     │  │ tello_rotate  │  │
│  │                  │  │ _temperature     │  │ tello_flip    │  │
│  │                  │  │ _humidity()      │  │ tello_get     │  │
│  │                  │  │                  │  │ _status()     │  │
│  └─────────────────┘  └───────┬──────────┘  └──────┬────────┘  │
│                               │                     │            │
│        Each robot is an       │                     │            │
│        isolated FastMCP       │                     │            │
│        instance               │                     │            │
└───────────────────────────────┼─────────────────────┼────────────┘
                                │                     │
                    ┌───────────▼──────┐   ┌──────────▼──────────┐
                    │ TumbllerClient   │   │   TelloClient       │
                    │ (HTTP/httpx)     │   │   (UDP/djitellopy)  │
                    └───────┬──────────┘   └──────────┬──────────┘
                            │                         │
                   HTTP :80 │                UDP :8889 │
                            ▼                         ▼
                    ┌───────────────┐       ┌──────────────────┐
                    │ ESP32-S3      │       │ DJI Tello        │
                    │ Tumbller      │       │ Drone            │
                    └───────────────┘       └──────────────────┘
```

---

## 10. Fake Rover — Software-Only Development Robot

To enable framework development and testing without physical hardware, the repo includes a **fake rover** — a pure-Python HTTP server that emulates the Tumbller's endpoint interface. It behaves identically from the MCP plugin's perspective: same paths, same response shapes, same timing semantics.

### 10.1. Why a Fake Rover?

- **No hardware needed** — develop and test the full plugin system on any machine
- **CI-friendly** — integration tests can spin up the fake rover, run MCP tools, and assert results
- **Plugin template validation** — the fake rover plugin is the simplest possible working example, ideal as a reference when adding real robots
- **Demo/onboarding** — new contributors can run the fleet gateway end-to-end in minutes

### 10.2. Fake Rover HTTP Server

A lightweight FastAPI app that mimics the Tumbller's ESP32 HTTP interface:

```python
# src/robots/fakerover/simulator.py

"""
Fake rover HTTP server — emulates Tumbller-compatible endpoints.

Run standalone:  uv run python -m robots.fakerover.simulator
Starts on port 8080 by default.
"""

import asyncio
import random
import time
from fastapi import FastAPI
import uvicorn

app = FastAPI(title="Fake Rover Simulator")

# Simulated state
_state = {
    "direction": "stop",
    "moving_since": None,
    "temperature": 22.5,
    "humidity": 45.0,
}

# Auto-stop durations (seconds), matching real Tumbller behavior
_AUTO_STOP = {
    "forward": 2.0,
    "back": 2.0,
    "left": 1.0,
    "right": 1.0,
}


def _drift_sensor():
    """Add small random drift to sensor readings for realism."""
    _state["temperature"] += random.uniform(-0.3, 0.3)
    _state["humidity"] += random.uniform(-0.5, 0.5)
    _state["temperature"] = round(max(15.0, min(35.0, _state["temperature"])), 1)
    _state["humidity"] = round(max(20.0, min(80.0, _state["humidity"])), 1)


@app.get("/motor/{direction}")
async def motor(direction: str):
    """Move the fake rover. Matches Tumbller endpoint behavior.

    forward/back auto-stop after 2s, left/right after 1s.
    Returns plain-text HTML like the real ESP32 firmware.
    """
    if direction == "stop":
        _state["direction"] = "stop"
        _state["moving_since"] = None
        return f"<h1>Motor: stop</h1>"

    if direction not in _AUTO_STOP:
        return {"error": f"Unknown direction: {direction}"}

    _state["direction"] = direction
    _state["moving_since"] = time.time()

    # Simulate auto-stop delay (non-blocking)
    duration = _AUTO_STOP[direction]

    async def auto_stop():
        await asyncio.sleep(duration)
        if _state["direction"] == direction:
            _state["direction"] = "stop"
            _state["moving_since"] = None

    asyncio.create_task(auto_stop())

    return f"<h1>Motor: {direction}</h1>"


@app.get("/info")
async def info():
    """Robot info endpoint. Returns JSON like the real Tumbller."""
    return {
        "name": "Fake Rover",
        "firmware": "simulator-1.0.0",
        "uptime_seconds": int(time.time()) % 86400,
        "direction": _state["direction"],
    }


@app.get("/sensor/ht")
async def sensor_ht():
    """Temperature and humidity sensor. Returns JSON with drifting values."""
    _drift_sensor()
    return {
        "temperature": _state["temperature"],
        "humidity": _state["humidity"],
    }


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8080)
```

### 10.3. Fake Rover Endpoints

Mirrors the real Tumbller exactly:

| Endpoint | Method | Response | Behavior |
|----------|--------|----------|----------|
| `/motor/forward` | GET | HTML `<h1>Motor: forward</h1>` | Auto-stops after 2s |
| `/motor/back` | GET | HTML `<h1>Motor: back</h1>` | Auto-stops after 2s |
| `/motor/left` | GET | HTML `<h1>Motor: left</h1>` | Auto-stops after 1s |
| `/motor/right` | GET | HTML `<h1>Motor: right</h1>` | Auto-stops after 1s |
| `/motor/stop` | GET | HTML `<h1>Motor: stop</h1>` | Immediate stop |
| `/info` | GET | JSON `{"name", "firmware", "uptime_seconds", "direction"}` | Always available |
| `/sensor/ht` | GET | JSON `{"temperature", "humidity"}` | Drifts randomly each read |

### 10.4. Fake Rover Plugin

The plugin reuses the same client pattern as Tumbller (httpx async GET), just pointed at the local simulator:

```python
# src/robots/fakerover/__init__.py

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
        return ["fakerover_move", "fakerover_is_online", "fakerover_get_temperature_humidity"]

    def register_tools(self, mcp):
        from .client import FakeRoverClient
        from .tools import register
        register(mcp, FakeRoverClient())
```

```python
# src/robots/fakerover/client.py

import os
import httpx


class FakeRoverClient:
    """HTTP client for the fake rover simulator.

    Identical interface to TumbllerClient — same .get() method,
    same response handling.
    """

    def __init__(self):
        self.base_url = os.getenv("FAKEROVER_URL", "http://localhost:8080")
        self.client = httpx.AsyncClient(base_url=self.base_url, timeout=5.0)

    async def get(self, path: str) -> dict:
        resp = await self.client.get(path)
        resp.raise_for_status()
        try:
            return resp.json()
        except Exception:
            return {"status": "ok", "body": resp.text}
```

```python
# src/robots/fakerover/tools.py

from typing import Literal
from fastmcp import FastMCP
from .client import FakeRoverClient


def register(mcp: FastMCP, robot: FakeRoverClient) -> None:
    """Register Fake Rover MCP tools on the server."""

    @mcp.tool
    async def fakerover_move(
        direction: Literal["forward", "back", "left", "right", "stop"],
    ) -> dict:
        """Move the fake rover in a given direction.
        forward/back auto-stop after 2 seconds, left/right after 1 second,
        stop halts motors immediately."""
        return await robot.get(f"/motor/{direction}")

    @mcp.tool
    async def fakerover_is_online() -> dict:
        """Check if the fake rover simulator is running and reachable."""
        try:
            await robot.get("/info")
            return {"online": True}
        except Exception:
            return {"online": False}

    @mcp.tool
    async def fakerover_get_temperature_humidity() -> dict:
        """Read simulated temperature (C) and humidity (%) from the fake rover."""
        return await robot.get("/sensor/ht")
```

### 10.5. Running the Fake Rover

```bash
# Terminal 1 — Start the simulator
uv run python -m robots.fakerover.simulator

# Terminal 2 — Start the MCP gateway with the fake rover plugin
uv run python scripts/serve.py --robots fakerover

# Or run both real and fake robots together
uv run python scripts/serve.py --robots fakerover tumbller --ngrok
```

Environment variable:
- `FAKEROVER_URL` — simulator address (default: `http://localhost:8080`)

### 10.6. Using Fake Rover for Testing

The fake rover enables automated integration tests without hardware:

```python
# Example test sketch
import subprocess, time, httpx

# Start simulator in background
sim = subprocess.Popen(["uv", "run", "python", "-m", "robots.fakerover.simulator"])
time.sleep(1)

# Test endpoints directly
r = httpx.get("http://localhost:8080/info")
assert r.status_code == 200
assert r.json()["name"] == "Fake Rover"

r = httpx.get("http://localhost:8080/motor/forward")
assert r.status_code == 200

r = httpx.get("http://localhost:8080/sensor/ht")
data = r.json()
assert "temperature" in data and "humidity" in data

sim.terminate()
```

---

## 11. Migration Path from Existing Repos

### Phase 0: Build the fake rover

1. Implement `src/robots/fakerover/simulator.py` (HTTP server emulating Tumbller endpoints)
2. Implement `FakeRoverPlugin` in `src/robots/fakerover/`
3. Verify: start simulator, then `uv run python scripts/serve.py --robots fakerover`
4. Use this to validate the entire plugin framework before porting real robots

### Phase 1: Create the framework repo

1. Create `robot-fleet-mcp` repo with the structure from Section 2
2. Move shared code (`tunnel.py`, `generate_wallet.py`, discovery, registration) into `src/core/`
3. Create `RobotPlugin` base class in `src/core/plugin.py`

### Phase 2: Port the Tumbller plugin

1. Copy `tumbller_client.py` → `src/robots/tumbller/client.py` (unchanged)
2. Extract tool definitions from `server.py` → `src/robots/tumbller/tools.py`
3. Write `TumbllerPlugin` class in `src/robots/tumbller/__init__.py`
4. Verify: `uv run python scripts/serve.py --robots tumbller`

### Phase 3: Port the Tello plugin

1. Copy `tello_client.py` → `src/robots/tello/client.py` (unchanged)
2. Extract tool definitions from `server.py` → `src/robots/tello/tools.py`
3. Write `TelloPlugin` class in `src/robots/tello/__init__.py`
4. Verify: `uv run python scripts/serve.py --robots tello`

### Phase 4: Add discovery MCP tool

1. Implement `register_discovery_tools()` in `src/core/discovery.py`
2. Wire it into `create_server()` so it's always loaded
3. Verify: connect Claude, call `discover_robot_agents()`

### Phase 5: Deprecate single-robot repos

1. Update original repos' READMEs pointing to the new framework
2. Archive `tumbller-8004-mcp` and `tello-8004-mcp`

---

## 12. Design Decisions

| # | Question | Decision | Rationale |
|---|----------|----------|-----------|
| 1 | **Single server or per-robot servers?** | **ASGI sub-mounts** — each robot gets its own isolated FastMCP instance, all mounted under one FastAPI gateway on a single port | Best of both worlds: per-robot isolation (separate tool namespaces, independent MCP sessions) with one process, one port, one ngrok tunnel. No subprocess management or reverse proxy needed. |
| 2 | **Tool prefixing** | **Always prefix** (`tumbller_move`, `tello_takeoff`) | Each robot has its own MCP server at its own path, so prefixes aren't strictly needed for uniqueness — but they're kept for clarity when an LLM reasons about tools from multiple robots. |
| 3 | **Plugin loading** | **Auto-discover + CLI override** | Auto-discover all packages in `src/robots/`, allow `--robots` flag to select a subset. |
| 4 | **One wallet per fleet or per robot?** | **Shared fleet wallet** (for now) | Simpler setup for dev/testing. Can migrate to per-robot wallets later for production isolation. |
| 5 | **Where does this repo live?** | **New repo `yakrover-8004-mcp`** | Cleaner separation from the single-robot repos. |

| 6 | **LLM auto-connection to robot endpoints?** | **Yes, include URLs** | Discovery response includes `local_endpoint` for each robot mounted on this gateway (null if not local). The LLM gets on-chain metadata + connection info in one call. |
| 7 | **Dynamic mount/unmount at runtime?** | **Static now, dynamic later** | Phase 1 uses static mounts at startup via `--robots` flag. The gateway keeps `robot_servers` as a mutable dict so dynamic mount/unmount can be added in Phase 2 without breaking changes. |
| 8 | **Fake rover for development?** | **Yes, included as `fakerover` plugin** | Emulates Tumbller HTTP endpoints (same paths, same response shapes) so the full framework can be developed and tested without physical hardware. Also serves as the simplest reference plugin implementation. |

---

## 13. Summary

**What changes:**
- Shared infrastructure code lives in one place (`core/`)
- Robot-specific code is isolated in plugin packages (`robots/{name}/`)
- Registration/update/fix scripts become generic, driven by plugin metadata
- Discovery becomes an MCP tool callable by LLMs
- Server architecture moves to ASGI sub-mounts (FastAPI gateway + per-robot FastMCP instances)

**What stays the same:**
- Each robot's client code is untouched (`TumbllerClient`, `TelloClient`)
- ERC-8004 registration flow is preserved
- ngrok tunneling is preserved (single tunnel for all robots)
- FastMCP as the MCP framework
- All existing robot affordances remain identical

**What's new:**
- `RobotPlugin` base class with 3 methods to implement
- Auto-discovery of plugins via package scanning
- `discover_robot_agents` MCP tool for LLM-driven robot discovery
- FastAPI gateway with ASGI sub-mounts — each robot at its own path (`/{name}/mcp`), one port, one ngrok tunnel
- Single `serve.py` that can load any combination of robots
- `_template/` directory for quickly scaffolding new robot plugins
- `fakerover` plugin — software-only simulator with Tumbller-compatible HTTP endpoints for hardware-free development and testing
