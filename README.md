# yakrover-8004-mcp

Modular MCP framework for multi-robot fleet control and on-chain discovery via [ERC-8004](https://eips.ethereum.org/EIPS/eip-8004).

A plugin-based architecture that consolidates shared infrastructure so any robot can be added with minimal glue code. Each robot gets its own isolated MCP server, all served behind a single port and ngrok tunnel.

## Architecture

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

## Prerequisites

- Python 3.13+
- [uv](https://docs.astral.sh/uv/) package manager
- [ngrok](https://ngrok.com/) account (free tier) for public tunnel
- Sepolia ETH for on-chain registration (free from [faucet](https://www.alchemy.com/faucets/ethereum-sepolia))
- [Pinata](https://www.pinata.cloud/) account (free tier) for IPFS uploads

## Quick Start

### 1. Clone and install

```bash
git clone git@github.com:YakRoboticsGarage/yakrover-8004-mcp.git
cd yakrover-8004-mcp
uv sync --extra fakerover
```

### 2. Configure environment

```bash
cp .env.example .env
```

### 3. Run the fake rover (no hardware needed)

```bash
# Terminal 1 — Start the simulator
PYTHONPATH=src uv run python -m robots.fakerover.simulator

# Terminal 2 — Start the MCP gateway
PYTHONPATH=src uv run python scripts/serve.py --robots fakerover
```

### 4. Connect an MCP client

```bash
# Claude Code
claude mcp add --transport http fakerover http://localhost:8000/fakerover/mcp
```

Then ask Claude to move the fake rover or read its temperature.

## Adding a Robot

Each robot is a plugin — a package under `src/robots/` with three files:

```
src/robots/myrobot/
├── __init__.py    # RobotPlugin subclass (metadata, tool names, registration)
├── client.py      # Communication with the physical robot
└── tools.py       # MCP tool definitions
```

See `src/robots/_template/` for a copyable starting point and `docs/MODULAR_FRAMEWORK_PLAN.md` Section 7 for a step-by-step guide.

## Install Options

```bash
uv sync                        # Core only (discovery + registration)
uv sync --extra fakerover      # With fake rover (no hardware needed)
uv sync --extra tumbller       # With Tumbller robot support
uv sync --extra tello          # With Tello drone support
uv sync --extra all            # Everything
```

## Project Structure

```
src/
  core/
    plugin.py              # RobotPlugin base class + RobotMetadata
    server.py              # FastAPI gateway + ASGI sub-mount orchestration
    tunnel.py              # ngrok tunnel helper
    discovery.py           # Robot discovery MCP tool (ERC-8004 queries)
    registration.py        # Generic on-chain registration
    wallet.py              # Ethereum wallet generation
  robots/
    fakerover/             # Software-only simulator (no hardware needed)
    tumbller/              # ESP32-S3 self-balancing robot (HTTP)
    tello/                 # DJI Tello drone (UDP)
    _template/             # Copyable scaffolding for new robots
scripts/
  serve.py                 # Start MCP server for one or more robots
  register.py              # Register a robot on-chain
  discover.py              # CLI robot discovery
  generate_wallet.py       # Ethereum wallet generator
docs/
  MODULAR_FRAMEWORK_PLAN.md  # Full design document
  DEVELOPMENT.md             # Implementation progress tracker
```

## Links

- [ERC-8004 Specification](https://eips.ethereum.org/EIPS/eip-8004)
- [8004scan Best Practices](https://best-practices.8004scan.io)
- [agent0_sdk](https://pypi.org/project/agent0-sdk/)
- [FastMCP](https://pypi.org/project/fastmcp/)
- [MCP Specification](https://spec.modelcontextprotocol.io)

## License

Apache 2.0 — see [LICENSE](LICENSE).
