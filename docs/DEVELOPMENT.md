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

- [x] Create `src/core/server.py` — `create_robot_server()`, `create_gateway()` with composed lifespans for FastMCP v3
- [x] Create `scripts/serve.py` — CLI entry point with `--robots` filter and `--port`
- [x] Verify: `uv run python scripts/serve.py --robots fakerover` starts gateway
- [x] Verify: `GET /` returns gateway info with mounted robots
- [x] Verify: `/fakerover/mcp` responds as a working MCP endpoint
- [x] Full MCP session verified: init, list tools, call `fakerover_move("forward")`, `fakerover_is_online`, `fakerover_get_temperature_humidity`

---

## Stage 4: Tunnel + Auth

Add ngrok tunnel support and optional bearer token auth.

- [x] Create `src/core/tunnel.py` — ngrok tunnel helper (ported from `tumbller-8004-mcp`)
- [x] Add `--ngrok` flag to `scripts/serve.py`
- [x] Add `MCP_BEARER_TOKEN` auth support in `create_robot_server()` (already done in Stage 3)
- [ ] Verify: `uv run python scripts/serve.py --robots fakerover --ngrok` creates tunnel, MCP works over public URL

---

## Stage 5: Port Tumbller Plugin

Port the real Tumbller robot from `tumbller-8004-mcp`. Client code is unchanged.

- [x] Create `src/robots/tumbller/__init__.py` — `TumbllerPlugin`
- [x] Copy `tumbller_client.py` → `src/robots/tumbller/client.py`
- [x] Create `src/robots/tumbller/tools.py` — extract tool defs from old `server.py`
- [x] Add `tumbller` optional dependency group in `pyproject.toml` (already present)
- [ ] Verify: `uv run python scripts/serve.py --robots tumbller --ngrok` — MCP tools work against real robot
- [ ] Verify: `uv run python scripts/serve.py --robots fakerover tumbller` — both mounted simultaneously

---

## Stage 6: Port Tello Plugin

Port the Tello drone from `tello-8004-mcp`. Client code is unchanged.

- [x] Create `src/robots/tello/__init__.py` — `TelloPlugin`
- [x] Copy `tello_client.py` → `src/robots/tello/client.py`
- [x] Create `src/robots/tello/tools.py` — extract tool defs from old `server.py`
- [x] Add `tello` optional dependency group in `pyproject.toml` (already present)
- [ ] Verify: `uv run python scripts/serve.py --robots tello` — MCP tools work against real drone

---

## Stage 7: On-Chain Registration

Generic registration scripts driven by plugin metadata, replacing per-robot registration scripts.

- [x] Create `src/core/registration.py` — `register_robot()`, `update_robot()`, `fix_metadata()` generic functions
- [x] Create `src/core/wallet.py` — wallet generation (port from existing)
- [x] Add `url_prefix` field to `RobotMetadata` — explicit URL path segment for MCP endpoint
- [x] Create `scripts/register.py` — CLI: `uv run python scripts/register.py tumbller`
- [x] Create `scripts/generate_wallet.py` — CLI wallet generation
- [x] Create `scripts/update_agent.py` — CLI: `uv run python scripts/update_agent.py tumbller 11155111:989`
- [x] Create `scripts/fix_metadata.py` — CLI: `uv run python scripts/fix_metadata.py tumbller 989`
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

---

## Key Findings and Lessons Learned

### Dependency Resolution

- **`agent0-sdk` requires a pre-release dependency** (`ipfshttpclient>=0.8.0a2`). uv won't resolve this by default — you must set `prerelease = "allow"` in `[tool.uv]` in `pyproject.toml`. The tumbller repo didn't need this because its lockfile was already resolved, but a fresh `uv sync` on a new repo will fail without it.

### FastMCP v3 Breaking Changes

- **`get_asgi_app()` is gone** — replaced by `http_app()` in FastMCP 3.x. The return type is `StarletteWithLifespan` (a Starlette app), which FastAPI can mount.
- **Lifespan management is mandatory** — FastMCP v3's `StreamableHTTPSessionManager` requires its task group to be initialized via the app's lifespan. When sub-mounting under FastAPI, you must compose all MCP app lifespans into the parent's lifespan, otherwise every request returns `500 Internal Server Error` with `RuntimeError: Task group is not initialized`.
- **Solution**: recursive `_compose_lifespans()` context manager that enters each MCP app's lifespan before yielding, passed to `FastAPI(lifespan=...)`.
- **Auth API unchanged** — `FastMCP(auth=...)` constructor param and `StaticTokenVerifier` still work the same in v3.

### Simulator Design

- **HTML responses matter** — the real Tumbller ESP32 firmware returns `text/html` for `/motor/*` endpoints (e.g. `<h1>Motor: forward</h1>`), not JSON. The simulator must use `HTMLResponse` to match this behavior, since `FakeRoverClient.get()` falls back to `{"status": "ok", "body": resp.text}` when `resp.json()` fails. Returning a plain string from FastAPI would auto-serialize to JSON instead.

### PYTHONPATH

- Scripts need `PYTHONPATH=src` or `sys.path.insert(0, "src")` because the package layout uses `src/core/` and `src/robots/` without a top-level installable package. `scripts/serve.py` handles this automatically with `sys.path.insert`, but running modules directly (e.g. `python -m robots.fakerover.simulator`) requires `PYTHONPATH=src`.
