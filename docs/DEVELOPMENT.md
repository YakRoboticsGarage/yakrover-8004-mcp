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

- [x] Create `src/core/discovery.py` — `discover_robots()` query function + `register_discovery_tools(mcp)`
- [x] Wire `create_fleet_server()` to mount discovery tools at `/fleet/mcp`
- [x] Create `scripts/discover.py` — CLI wrapper for discovery
- [x] Store `fleetEndpoint` in IPFS agent card during registration so discovery can surface it
- [x] Fix discovery to always fetch IPFS metadata (not just when subgraph lacks tools) so `fleet_endpoint` is always populated
- [x] Add `mcp_endpoint` to discovery results — read from IPFS agent card `endpoint` field
- [x] Verify: connect Claude to `/fleet/mcp`, call `discover_robot_agents()`
- [x] Verify: discovery response includes `mcp_endpoint` and `fleet_endpoint` from IPFS

---

## Stage 9: Discovery CLI — MCP Config Writer

Add `--add-mcp` flag to `scripts/discover.py` so discovered robots can be auto-added to Claude's MCP config.

- [x] Add `--add-mcp` flag — writes discovered endpoints as MCP servers to Claude config
- [x] Add `--scope` flag — `project` (`.mcp.json`) or `global` (`~/.claude.json`), default `project`
- [x] Load `MCP_BEARER_TOKEN` from `.env` for auth headers
- [x] Derive server names from fleet domain + robot name (e.g. `finland-tumbller`, `finland-fleet`)
- [x] Deduplicate fleet endpoints across robots sharing the same fleet
- [x] Update README with `--add-mcp` usage and scope table
- [x] Verify: `uv run python scripts/discover.py --add-mcp` writes correct `.mcp.json`
- [x] Verify: `uv run python scripts/discover.py --add-mcp --scope global` writes correct `~/.claude.json`

---

## Stage 10: Cleanup + Deprecation

Final polish and migration away from single-robot repos.

- [ ] Add `all` optional dependency group to `pyproject.toml`
- [ ] Update `tumbller-8004-mcp` README pointing to this repo
- [ ] Update `tello-8004-mcp` README pointing to this repo
- [ ] Archive old single-robot repos

---

## Phase 2: Bidding Marketplace

Implementation of the robot-side bidding marketplace. See [BIDDING_MARKETPLACE_PLAN.md](BIDDING_MARKETPLACE_PLAN.md) for full design.

The external marketplace (`yakrover-marketplace`) calls robot MCP tools directly. This repo implements the robot side: bid evaluation, task execution, on-chain bidding terms, and payment receipt.

**Stages 1, 2, and 3 complete.** Next: Stage 5b (standardise `execute()` delivery format across all plugins), then Stage 4 (Stripe payment integration), Stage 5 (approval flow), Stage 5c (feedback tool).

---

### Stage 6: Multi-Chain Support

Add `--chain` flag to all CLI scripts so robots can be registered and discovered on any supported EVM chain. Single source of truth for chain config in `src/core/chains.py`.

- [x] Create `src/core/chains.py` — `CHAINS` config map (`eth-sepolia`, `eth-mainnet`, `base-sepolia`, `base-mainnet`); `get_chain()` resolves explicit arg → `CHAIN` env var → `eth-sepolia` default; returns `{name, chain_id, rpc}` dict
- [x] Update `src/core/registration.py` — `_make_sdk()`, `register_robot()`, `update_robot()`, `fix_metadata()` all accept `chain: str | None`; `RPC_URL` env override preserved; chain name printed in status messages
- [x] Update `src/core/discovery.py` — `_get_sdk()` and `discover_robots()` accept `chain`; `discover_robot_agents` MCP tool exposes `chain` param to LLM clients
- [x] Add `--chain` flag to `scripts/register.py`
- [x] Add `--chain` flag to `scripts/discover.py` (also prints chain name/ID in query header)
- [x] Add `--chain` flag to `scripts/update_agent.py`
- [x] Add `--chain` flag to `scripts/fix_metadata.py`
- [ ] Verify: `uv run python scripts/register.py tumbller --chain base-mainnet` — registers on Base mainnet
- [ ] Verify: `uv run python scripts/discover.py --provider yakrover --chain base-sepolia` — queries Base Sepolia
- [ ] Verify: `CHAIN=base-mainnet uv run python scripts/discover.py` — env var respected

---

### Stage 1: Auction Engine Core (`src/auction/`)

- [x] **1a** — Create `src/auction/models.py` — `TaskSpec`, `Bid`, `AuctionResult` dataclasses
- [x] **1b** — Create `src/auction/engine.py` — `AuctionEngine` (bid fan-out, acceptance, execution, `busy` set for concurrency guard)
- [x] **1c** — Create `src/auction/mcp_tools.py` — fleet-level tools: `fleet_request_bids`, `fleet_list_auctions`, `fleet_accept_bid`, `fleet_execute_task`, `fleet_get_auction_status`

---

### Stage 1d: Robot-Side MCP Tools

Shared helper that registers marketplace tools on each robot's MCP server. External marketplace calls these directly at `/{robot}/mcp`.

- [x] Create `src/core/marketplace_tools.py` — registers `robot_submit_bid`, `robot_execute_task`, `robot_get_pricing` on any robot MCP server
- [x] Call `marketplace_tools` in `create_robot_server()` so all plugins get the tools automatically
- [x] Add the three tool names to each plugin's `tool_names()` list

---

### Stage 2: Plugin Bid Implementations

- [x] **2a** — `src/robots/tumbller/__init__.py` — override `bid()` (env_sensing / sensor_reading, liveness check) and `execute()` (temperature/humidity reading, delivery_data format)
- [x] **2b** — `src/robots/fakerover/__init__.py` — align existing `bid()` to Bid schema (price float, `ai_confidence` → `confidence`, `capability_metadata` → `capabilities_offered` flat list, add `currency` + `notes`); add `execute()` and `bidding_terms` to `metadata()`
- [x] **2c** — `src/robots/tello/__init__.py` — override `bid()` (camera tasks) and `execute()` (photo/video, delivery_data format)

---

### Stage 3: Bidding Terms in On-Chain Metadata

- [x] Add `BiddingTerms` dataclass and `bidding_terms` field to `RobotMetadata` in `src/core/plugin.py`
- [x] Update `registration.py` — serialize bidding terms as flat keys (`min_bid_price`, `accepted_currencies`, `task_categories`) into the IPFS agent card via `_build_metadata()` helper in both `register_robot()` and `update_robot()`
- [x] Update `discovery.py` — parse bidding terms from fetched agent card JSON via `_parse_bidding_terms()` and include in discovery result as `bidding_terms` key

---

### Stage 4: Payment Integration

- [ ] Create `src/auction/payments.py` — `StripePaymentHandler` (checkout session creation, webhook verification)
- [ ] Create `src/auction/webhooks.py` — FastAPI `/stripe/webhook` route
- [ ] Wire webhook route into gateway in `server.py`
- [ ] Add `stripe` to `pyproject.toml` as optional `marketplace` extra
- [ ] Document `STRIPE_SECRET_KEY`, `STRIPE_WEBHOOK_SECRET`, `STRIPE_CONNECT_ACCOUNT_ID` in `.env.example`

---

### Stage 5: Approval Flow + Delivery Format

- [ ] **5b** — Standardize `execute()` return across all plugins: `{success, delivery_data: {readings, summary, robot_id, robot_name, duration_seconds}}` / `{success: false, error, partial_data}`
- [ ] **5** — Implement `requires_approval` flag from `BiddingTerms`; Mode A (human-in-the-loop) and Mode B (autonomous) execution paths in `AuctionEngine`
- [ ] **5c** — Wire `auction_submit_feedback` call after successful delivery (optional for v1; blocked on marketplace MCP reachability)

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

### IPFS Agent Card and Discovery

- **Always fetch IPFS metadata** — the agent0-sdk subgraph may already index `mcp_tools`, but `fleet_endpoint` and `mcp_endpoint` are only stored in the IPFS agent card. Discovery must always fetch IPFS metadata regardless of whether the subgraph has tools, otherwise fleet/MCP URLs come back null.
- **IPFS field naming mismatch** — the IPFS agent card stores the MCP service URL as `endpoint` (not `mcp_endpoint`). Discovery must map `card["endpoint"]` → `mcp_endpoint` in the output dict.
- **Store fleet endpoint at registration time** — `fleetEndpoint` must be written into the IPFS agent card during `register.py`, not just assumed from the ngrok domain. This ensures anyone discovering the robot gets the fleet URL without needing to derive it.

### PYTHONPATH

- Scripts need `PYTHONPATH=src` or `sys.path.insert(0, "src")` because the package layout uses `src/core/` and `src/robots/` without a top-level installable package. `scripts/serve.py` handles this automatically with `sys.path.insert`, but running modules directly (e.g. `python -m robots.fakerover.simulator`) requires `PYTHONPATH=src`.
