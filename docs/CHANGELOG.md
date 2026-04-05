# Changelog

## 0.2.0 — 2026-04-05

### Added

- **Auction engine core (Stage 1a/1b)** — `src/auction/` package with data models and engine.
  - `src/auction/models.py` — `TaskSpec`, `Bid`, and `AuctionResult` dataclasses. `AuctionResult` tracks full lifecycle state (`"bidding" → "accepted" → "executing" → "completed"/"failed"`) via `auction_id`.
  - `src/auction/engine.py` — `AuctionEngine` fans out `plugin.bid()` calls in parallel via `asyncio.gather`, filters bids that exceed `budget_ceiling`, tracks busy robots in `self._busy` to prevent double-booking, and captures execution errors into `AuctionResult` rather than crashing.
- **Robot-side marketplace tools (Stage 1d)** — `src/core/marketplace_tools.py` registers `robot_submit_bid`, `robot_execute_task`, and `robot_get_pricing` on every robot's MCP server automatically via `create_robot_server()`. No per-plugin code required.
  - `robot_submit_bid` — delegates to `plugin.bid()`, normalises response to the `Bid` schema.
  - `robot_execute_task` — delegates to `plugin.execute()`. `payment_source` param documents call origin but does not affect execution logic.
  - `robot_get_pricing` — reads `BiddingTerms` from plugin metadata via `getattr` so it returns safe defaults now and picks up real values when Stage 3 adds `BiddingTerms` to `RobotMetadata`.
- **`execute()` stub on `RobotPlugin`** — default implementation returns `{"success": False, "error": "..."}` so the engine marks auctions as `"failed"` rather than raising `AttributeError` on unimplemented plugins.
- **`MARKETPLACE_TOOL_NAMES` constant** — exported from `marketplace_tools.py`; `tool_names()` on all three plugins (fakerover, tumbller, tello) updated to include the three marketplace tool names for on-chain registration.

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
