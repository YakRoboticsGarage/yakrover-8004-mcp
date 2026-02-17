# Development Progress

Tracking implementation of the modular robot MCP framework.
See [MODULAR_FRAMEWORK_PLAN.md](MODULAR_FRAMEWORK_PLAN.md) for full design.

---

## Stage 1: Project Skeleton + Plugin Base

Set up the repo structure, dependency management, and the plugin abstraction that everything else builds on. No robots yet — just the bones.

- [x] Create `pyproject.toml` with core dependencies (fastmcp, fastapi, uvicorn, agent0-sdk, pyngrok, web3, python-dotenv, requests)
- [x] Create `.env.example` with all expected env vars
- [x] Create `src/core/__init__.py`
- [x] Create `src/core/plugin.py` — `RobotPlugin` ABC + `RobotMetadata` dataclass
- [x] Create `src/robots/__init__.py` — `discover_plugins()` auto-discovery function
- [x] Create `src/robots/_template/` — copyable scaffolding (`__init__.py`, `client.py`, `tools.py`)
- [x] Verify: `uv sync` succeeds, `discover_plugins()` returns empty dict

---

## Stage 2: Fake Rover Simulator

Build the fake rover HTTP server first — it gives us something to test against without any hardware.

- [x] Create `src/robots/fakerover/__init__.py` — `FakeRoverPlugin` class
- [x] Create `src/robots/fakerover/client.py` — `FakeRoverClient` (httpx, same interface as TumbllerClient)
- [x] Create `src/robots/fakerover/tools.py` — `register(mcp, robot)` with `fakerover_move`, `fakerover_is_online`, `fakerover_get_temperature_humidity`
- [x] Create `src/robots/fakerover/simulator.py` — FastAPI app emulating Tumbller endpoints (`/motor/{direction}`, `/info`, `/sensor/ht`)
- [x] Add `fakerover` optional dependency group in `pyproject.toml` (`httpx>=0.28.1`)
- [x] Verify: `uv run python -m robots.fakerover.simulator` starts on :8080, endpoints respond correctly
- [x] Verify: `discover_plugins()` finds `FakeRoverPlugin`

---

## Stage 3: Gateway + MCP Server

Wire up the FastAPI gateway with ASGI sub-mounts so each robot gets its own isolated MCP server at `/{name}/mcp`.

- [ ] Create `src/core/server.py` — `create_robot_server()`, `create_fleet_server()`, `create_gateway()`
- [ ] Create `scripts/serve.py` — CLI entry point with `--robots` filter and `--port`
- [ ] Verify: `uv run python scripts/serve.py --robots fakerover` starts gateway
- [ ] Verify: `GET /` returns gateway info with mounted robots
- [ ] Verify: `/fakerover/mcp` responds as a working MCP endpoint
- [ ] Connect Claude Desktop / MCP client to `/fakerover/mcp`, call `fakerover_move("forward")` end-to-end

---

## Stage 4: Tunnel + Auth

Add ngrok tunnel support and optional bearer token auth.

- [ ] Create `src/core/tunnel.py` — ngrok tunnel helper (port from `tumbller-8004-mcp`)
- [ ] Add `--ngrok` flag to `scripts/serve.py`
- [ ] Add `MCP_BEARER_TOKEN` auth support in `create_robot_server()` and `create_fleet_server()`
- [ ] Verify: `uv run python scripts/serve.py --robots fakerover --ngrok` creates tunnel, MCP works over public URL

---

## Stage 5: Port Tumbller Plugin

Port the real Tumbller robot from `tumbller-8004-mcp`. Client code is unchanged.

- [ ] Create `src/robots/tumbller/__init__.py` — `TumbllerPlugin`
- [ ] Copy `tumbller_client.py` → `src/robots/tumbller/client.py`
- [ ] Create `src/robots/tumbller/tools.py` — extract tool defs from old `server.py`
- [ ] Add `tumbller` optional dependency group in `pyproject.toml`
- [ ] Verify: `uv run python scripts/serve.py --robots tumbller --ngrok` — MCP tools work against real robot
- [ ] Verify: `uv run python scripts/serve.py --robots fakerover tumbller` — both mounted simultaneously

---

## Stage 6: Port Tello Plugin

Port the Tello drone from `tello-8004-mcp`. Client code is unchanged.

- [ ] Create `src/robots/tello/__init__.py` — `TelloPlugin`
- [ ] Copy `tello_client.py` → `src/robots/tello/client.py`
- [ ] Create `src/robots/tello/tools.py` — extract tool defs from old `server.py`
- [ ] Add `tello` optional dependency group in `pyproject.toml`
- [ ] Verify: `uv run python scripts/serve.py --robots tello` — MCP tools work against real drone

---

## Stage 7: On-Chain Registration

Generic registration scripts driven by plugin metadata, replacing per-robot registration scripts.

- [ ] Create `src/core/registration.py` — `register_robot(plugin)` generic function
- [ ] Create `src/core/wallet.py` — wallet generation (port from existing)
- [ ] Create `scripts/register.py` — CLI: `uv run python scripts/register.py tumbller`
- [ ] Create `scripts/generate_wallet.py` — CLI wallet generation
- [ ] Verify: register fakerover on-chain (Sepolia testnet)
- [ ] Verify: register tumbller on-chain, confirm agent ID + metadata match

---

## Stage 8: Discovery MCP Tool

Turn `discover_robot_agent.py` into an MCP tool on the fleet server so LLMs can discover robots at runtime.

- [ ] Create `src/core/discovery.py` — `discover_robots()` query function + `register_discovery_tools(mcp)`
- [ ] Wire `create_fleet_server()` to mount discovery tools at `/fleet/mcp`
- [ ] Create `scripts/discover.py` — CLI wrapper for discovery
- [ ] Verify: connect Claude to `/fleet/mcp`, call `discover_robot_agents()`
- [ ] Verify: discovery response includes `local_endpoint` for locally mounted robots

---

## Stage 9: Cleanup + Deprecation

Final polish and migration away from single-robot repos.

- [ ] Add `all` optional dependency group to `pyproject.toml`
- [ ] Update `tumbller-8004-mcp` README pointing to this repo
- [ ] Update `tello-8004-mcp` README pointing to this repo
- [ ] Archive old single-robot repos
