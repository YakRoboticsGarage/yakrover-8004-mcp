# Changelog

## 0.4.0 — 2026-04-05

### Added

Completes **Stage 4** (payment integration) and **Stage 5** (approval flow + delivery format).

- **Stage 4a — `src/auction/payments.py`**: `StripePaymentHandler` wraps `stripe.checkout.Session.create()` and `stripe.Webhook.construct_event()`. `create_checkout_session()` builds a Checkout session with `auction_id` in metadata and correct success/cancel redirect URLs derived from `NGROK_DOMAIN`. `handle_webhook()` verifies the Stripe signature and returns `auction_id` on `checkout.session.completed`.
- **Stage 4b — `src/auction/webhooks.py`**: `make_stripe_webhook_route(payment_handler, engine)` returns a FastAPI route handler for `POST /stripe/webhook`. On signature validation failure returns HTTP 400; on success calls `engine.on_payment_confirmed()`.
- **Stage 4c/4d — `src/core/server.py`**: `create_gateway()` now reads `STRIPE_SECRET_KEY` and `STRIPE_WEBHOOK_SECRET` from the environment; if both are set and the `stripe` package is installed, a `StripePaymentHandler` is instantiated and passed to `AuctionEngine`. The `/stripe/webhook` route is mounted only when Stripe is active. Gateway index (`GET /`) exposes `"stripe_webhook": "/stripe/webhook"` when enabled.
- **Stage 4e — `pyproject.toml`**: `stripe>=7.0.0` added as optional `marketplace` extra (`uv sync --extra marketplace`). Also included in `all`.
- **Stage 4f — `.env.example`**: Documents `STRIPE_SECRET_KEY`, `STRIPE_WEBHOOK_SECRET`, and `STRIPE_CONNECT_ACCOUNT_ID` with setup notes.
- **Stage 5 — Approval flow** (`src/auction/engine.py`):
  - `AuctionEngine.__init__` accepts `payment_handler` parameter.
  - `accept_bid()` creates a Stripe Checkout session when a payment handler is configured and stores the URL in `auction.stripe_checkout_url`.
  - New `on_payment_confirmed(auction_id)` method: marks `status = "paid"`, reads `requires_approval` from the winning plugin's `BiddingTerms`, and schedules auto-execution via `asyncio.create_task()` when `requires_approval=False` (Mode B). Waits for operator approval otherwise (Mode A).
  - `execute()` now accepts auctions in `"accepted"` status (USDC / no-payment path) **or** `"paid"` status (Stripe payment confirmed). Error message updated.
- **Stage 5b — Delivery format**: All three plugin `execute()` implementations (FakeRover, Tumbller, Tello) already return the standardized `{success, delivery_data: {readings, summary, robot_id, robot_name, duration_seconds}}` structure. No code changes required.
- **`fleet_execute_task` docstring** (`src/auction/mcp_tools.py`): Updated to document Mode A / Mode B distinction and the "accepted" or "paid" status requirement.

---

## 0.3.0 — 2026-04-05

### Added

Completes **Stage 2** (plugin bid implementations) and **Stage 3** (bidding terms in on-chain metadata).

- **`BiddingTerms` dataclass** (`src/core/plugin.py`) — `min_price_cents`, `rate_per_minute_cents`, `currency`, `accepted_task_types`, `max_duration_secs`, `max_concurrent_tasks`, `requires_approval`. Added as optional `bidding_terms` field on `RobotMetadata`; `None` means the robot does not participate in the marketplace.
- **Stage 2b — FakeRover** (`src/robots/fakerover/__init__.py`): aligned `bid()` to the `Bid` schema (`price` float, `ai_confidence` → `confidence`, `capability_metadata` → `capabilities_offered` flat list, added `currency` and `notes`); added task-category filter (`env_sensing` / `sensor_reading`); added budget check; implemented `execute()` returning `delivery_data` with AHT20 sensor readings; added `bidding_terms` ($0.50 min, $0.10/min, sensor_reading tasks).
- **Stage 2a — Tumbller** (`src/robots/tumbller/__init__.py`): `bid()` filters on `env_sensing` / `sensor_reading`, checks capability subset (`temperature`, `humidity`), enforces budget floor, does a liveness `/info` call; `execute()` reads `/sensor/ht` and returns `delivery_data` with SHT3x readings; `bidding_terms` set ($0.50 min, $0.10/min, sensor_reading tasks, 60 s max).
- **Stage 2c — Tello** (`src/robots/tello/__init__.py`): `bid()` filters on `visual_inspection` / `camera`, enforces budget floor, does a liveness `is_online()` call; `execute()` takes off, captures in-flight attitude + status telemetry, lands, and returns `delivery_data`; `bidding_terms` set ($1.00 min, $0.50/min, camera tasks, 300 s max).
- **Stage 3b — `registration.py`**: new `_build_metadata()` helper serialises `BiddingTerms` as flat string keys (`min_bid_price`, `accepted_currencies`, `task_categories`) into the IPFS agent card alongside the four base keys. Internal task type names (`sensor_reading`, `camera`) are translated to marketplace vocabulary (`env_sensing`, `visual_inspection`) on write. Both `register_robot()` and `update_robot()` now call `_build_metadata()`.
- **Stage 3c — `discovery.py`**: new `_parse_bidding_terms()` helper reads the flat metadata keys from the fetched agent card and returns a structured dict. `_fetch_ipfs_mcp_meta()` now includes `biddingTerms` in its result when present. `discover_robots()` surfaces `bidding_terms` on each robot entry. `discover_robot_agents` MCP tool docstring updated.

---

## 0.2.0 — 2026-04-05

### Added

Completes **Stage 1** of the bidding marketplace. The external marketplace can now call `robot_submit_bid` / `robot_execute_task` on any robot's MCP endpoint, and LLM clients on `/fleet/mcp` can run the full bid → accept → execute flow via the fleet tools.

- **Stage 1a — Data models** (`src/auction/models.py`): `TaskSpec`, `Bid`, and `AuctionResult` dataclasses. `AuctionResult` carries an `auction_id` and tracks lifecycle state through `"bidding" → "accepted" → "executing" → "completed"/"failed"`.
- **Stage 1b — Auction engine** (`src/auction/engine.py`): `AuctionEngine` fans out `plugin.bid()` calls across all plugins in parallel via `asyncio.gather`, filters bids exceeding `budget_ceiling`, guards against double-booking with a `_busy` set, and captures execution errors into `AuctionResult` rather than crashing. Explicit `None` guard on `winning_bid` before dereferencing in `execute()`.
- **Stage 1c — Fleet MCP tools** (`src/auction/mcp_tools.py`): five LLM-facing tools on `/fleet/mcp` — `fleet_request_bids`, `fleet_list_auctions`, `fleet_accept_bid`, `fleet_execute_task`, `fleet_get_auction_status`. `AuctionEngine` is instantiated in `create_gateway()` and wired into the fleet server automatically.
- **Stage 1d — Robot-side marketplace tools** (`src/core/marketplace_tools.py`): shared `register(mcp, plugin)` adds `robot_submit_bid`, `robot_execute_task`, and `robot_get_pricing` to every robot's MCP server via `create_robot_server()` — no per-plugin code required.
  - `robot_submit_bid` — delegates to `plugin.bid()`, normalises response to the `Bid` schema, and enforces the `budget_ceiling` filter before returning an affirmative bid.
  - `robot_execute_task` — delegates to `plugin.execute()`; `payment_source` param documents call origin but does not affect execution.
  - `robot_get_pricing` — derives `accepted_currencies` from `BiddingTerms.currency` when present; uses explicit `is not None` for `rate_per_minute_cents` so a zero rate and a flat-price-only (`None`) are distinguishable; returns safe defaults until Stage 3 adds `BiddingTerms` to `RobotMetadata`.
- **`RobotPlugin.execute()` stub** — returns `{"success": False, "error": "..."}` so the engine marks auctions `"failed"` gracefully on unimplemented plugins.
- **All three plugins updated** — `tool_names()` on fakerover, tumbller, and tello include the three marketplace tool names for on-chain registration.

---

## 0.1.0 — 2026-04-05

### Added

- **Multi-chain support (Stage 6)** — EVM chain selection for all registration and discovery operations. Supports `eth-sepolia`, `eth-mainnet`, `base-sepolia`, and `base-mainnet`.
  - New `src/core/chains.py` — single source of truth for chain IDs and default RPC URLs. `get_chain()` resolves via explicit arg → `CHAIN` env var → `eth-sepolia` default.
  - `--chain` flag on all four CLI scripts (`register.py`, `discover.py`, `update_agent.py`, `fix_metadata.py`).
  - `discover_robot_agents` MCP tool gains a `chain` parameter so LLMs can query across chains.
  - `RPC_URL` in `.env` still overrides the chain's default RPC for power users.
  - No breaking change — all commands default to `eth-sepolia` as before.

---

## 0.0.1 — 2026-02-25

Initial release of the modular MCP framework for multi-robot fleet control and on-chain discovery via ERC-8004.

### Added

- **Plugin system** — `RobotPlugin` base class with auto-discovery; add a robot by dropping a package into `src/robots/`
- **FastAPI gateway** — ASGI sub-mounts give each robot an isolated FastMCP server at `/{robot}/mcp`, all behind a single port
- **ngrok tunnel** — `--ngrok` flag on `serve.py` for public access with optional bearer token auth
- **Fake rover simulator** — hardware-free development plugin emulating Tumbller HTTP endpoints
- **Tumbller plugin** — ESP32-S3 self-balancing robot control over HTTP (`tumbller_move`, `tumbller_is_online`, `tumbller_get_temperature_humidity`)
- **Tello plugin** — DJI Tello drone control over UDP (`tello_takeoff`, `tello_land`, `tello_move`, `tello_rotate`, `tello_flip`, `tello_get_status`)
- **On-chain registration** — `register.py`, `update_agent.py`, `fix_metadata.py` scripts for ERC-8004 agent registration on Ethereum Sepolia with IPFS metadata
- **Fleet discovery MCP tool** — `discover_robot_agents()` tool on `/fleet/mcp` so LLMs can discover robots at runtime by querying the blockchain
- **Discovery CLI** — `discover.py` with `--type` and `--provider` filters
- **MCP config writer** — `discover.py --add-mcp` auto-adds discovered robots to Claude's MCP config (project or global scope) with bearer token auth from `.env`
- **Wallet generation** — `generate_wallet.py` for Ethereum key pair creation

### Fixed

- Discovery now always fetches IPFS metadata so `fleet_endpoint` is populated even when the subgraph already has tool names
- `mcp_endpoint` included in discovery results (read from IPFS agent card `endpoint` field)
- `fleetEndpoint` stored in IPFS agent card at registration time so it's available to anyone discovering the robot
