# CLAUDE.md — yakrover-8004-mcp

## Project Overview

Modular MCP framework for multi-robot fleet control and on-chain discovery via ERC-8004. Consolidates shared infrastructure from `tumbller-8004-mcp` and `tello-8004-mcp` into a single plugin-based architecture.

## Repository Structure

```
yakrover-8004-mcp/
├── src/
│   ├── core/           # Shared infrastructure (never changes per robot)
│   │   ├── server.py   # FastAPI gateway + ASGI sub-mount orchestration
│   │   ├── tunnel.py   # ngrok tunnel
│   │   ├── discovery.py # Robot discovery + MCP tool (ERC-8004 on-chain queries)
│   │   ├── registration.py # Generic ERC-8004 register/update/fix
│   │   ├── wallet.py   # Wallet generation
│   │   └── plugin.py   # RobotPlugin base class + RobotMetadata dataclass
│   └── robots/         # One sub-package per robot type
│       ├── tumbller/   # ESP32-S3 self-balancing robot (HTTP/httpx)
│       ├── tello/      # DJI Tello drone (UDP/djitellopy)
│       ├── fakerover/   # Software-only simulator (no hardware needed)
│       └── _template/  # Copyable scaffolding for new robots
├── scripts/            # CLI entry points (serve.py, register.py, discover.py, generate_wallet.py)
└── docs/
```

## Architecture

- **FastAPI gateway** with ASGI sub-mounts — each robot gets its own isolated FastMCP server instance
- Single port, single ngrok tunnel serves all robots
- Endpoints: `/fleet/mcp` (discovery/orchestration), `/{robot}/mcp` (per-robot control)
- Plugin auto-discovery scans `src/robots/` for `RobotPlugin` subclasses

## Plugin System

Each robot plugin is a package under `src/robots/{name}/` with three files:

- `__init__.py` — `RobotPlugin` subclass with `metadata()`, `tool_names()`, `register_tools(mcp)`
- `client.py` — robot-specific communication (HTTP, UDP, serial, etc.)
- `tools.py` — `register(mcp, client)` function that defines `@mcp.tool` handlers

Tool naming convention: `{robot_prefix}_{action}` (e.g. `tumbller_move`, `tello_takeoff`).

## Key Technologies

- **Python 3.13+**, managed with `uv`
- **FastMCP** — MCP server framework
- **FastAPI + uvicorn** — ASGI gateway
- **agent0-sdk** — ERC-8004 on-chain registration and discovery (Ethereum Sepolia)
- **pyngrok** — tunnel management
- **web3** — blockchain interaction

## Common Commands

```bash
# Install dependencies
uv sync                        # Core only
uv sync --extra tumbller       # With Tumbller support
uv sync --extra tello          # With Tello support
uv sync --extra fakerover       # With fake rover (no hardware needed)
uv sync --extra all            # Everything

# Serve robots
uv run python scripts/serve.py --ngrok                          # All robots
uv run python scripts/serve.py --robots tumbller --ngrok        # Single robot
uv run python scripts/serve.py --robots tumbller tello --ngrok  # Multi-select

# Fake rover (hardware-free development)
uv run python -m robots.fakerover.simulator                      # Start simulator on :8080
uv run python scripts/serve.py --robots fakerover                # MCP gateway for fake rover

# Register a robot on-chain
uv run python scripts/register.py tumbller

# Generate wallet
uv run python scripts/generate_wallet.py

# Run discovery CLI
uv run python scripts/discover.py
```

## Environment Variables

Required in `.env`:
- `RPC_URL` — Ethereum Sepolia RPC endpoint
- `SIGNER_PVT_KEY` — Wallet private key for on-chain transactions
- `PINATA_JWT` — Pinata API token for IPFS uploads
- `NGROK_DOMAIN` — ngrok static domain
- `MCP_BEARER_TOKEN` — (optional) Bearer token for MCP auth
- `FAKEROVER_URL` — (optional) Fake rover simulator address (default: `http://localhost:8080`)

## Development Guidelines

- When adding a new robot, create a package under `src/robots/` — see `src/robots/_template/` or `docs/MODULAR_FRAMEWORK_PLAN.md` Section 7
- Robot client code is fully self-contained; do not put robot-specific logic in `src/core/`
- Add robot-specific dependencies as optional extras in `pyproject.toml`
- No framework code changes should be needed to add a new robot
- Shared fleet wallet is used (single signer key for all robots)
- Use the `fakerover` plugin for development/testing without physical hardware — it emulates Tumbller HTTP endpoints (`/motor/*`, `/info`, `/sensor/ht`)
