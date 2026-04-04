# Robot Bidding Marketplace — Implementation Plan

## Overview

Add the ability for robots in the fleet to **receive task requests, generate bids, execute paid work, and get paid** — via USDC on-chain (primary) or Stripe credit card (optional). The external YAK ROBOTICS marketplace orchestrates the auction; this repo implements the robot side.

```
1. DISCOVER    Robot registered on ERC-8004. Marketplace finds it.
2. BID         Buyer posts task → marketplace calls robot_submit_bid → robot evaluates and returns price.
3. AWARD       Buyer picks a winner. Robot is notified via task acceptance.
4. EXECUTE     Marketplace calls robot_execute_task → robot does the work.
5. DELIVER     Robot returns structured JSON. Marketplace uploads to IPFS.
6. VERIFY      Buyer reviews data via IPFS link.
7. PAY         Buyer releases payment → 88% to robot wallet (USDC) or Stripe account (card).
```

**This repo's responsibility:** steps 2 and 4 — expose `robot_submit_bid`, `robot_execute_task`, and `robot_get_pricing` as MCP tools on each robot's server, and keep on-chain metadata up to date.

---

## What Already Exists

| Component | Status | Location |
|-----------|--------|----------|
| `RobotPlugin.bid(task_spec)` stub | Returns `None` (opt-out) | `src/core/plugin.py:46-52` |
| `auction_engine` parameter in `create_fleet_server` | Wired but unused — imports `auction.mcp_tools` | `src/core/server.py:39-68` |
| `auction/` package | **Does not exist yet** | — |
| On-chain metadata (category, robot_type, etc.) | Working | `src/core/registration.py` |
| Stripe integration | **Does not exist yet** | — |

---

## Architecture

Two layers — external marketplace calling robot tools, and internal fleet orchestration for LLM clients:

```
External Marketplace (yakrover-marketplace)
  │
  ├─ calls robot_submit_bid ──► Robot MCP Server (/{robot}/mcp)
  │                               └─ plugin.bid() logic
  │
  ├─ calls robot_execute_task ──► Robot MCP Server
  │                               └─ actual sensor/camera work
  │
  ├─ calls robot_get_pricing ──► Robot MCP Server
  │                               └─ BiddingTerms from metadata()
  │
  ├─ payment: USDC ──► robot on-chain wallet (getAgentWallet, 88%)
  │           card  ──► Stripe Connect Express account (88%)
  │                     platform keeps 12% commission either way
  │
  └─ uploads delivery_data to IPFS, returns CID to buyer

Internal Fleet Server (/fleet/mcp) — for LLM clients on this gateway
  │
  ├─ fleet_request_bids ──► AuctionEngine ──► plugin.bid() (all plugins)
  ├─ fleet_accept_bid
  ├─ fleet_execute_task
  └─ fleet_get_auction_status
```

---

## Stages

### Stage 1: Auction Engine Core (`src/auction/`)

Create `src/auction/` as a new internal package (not a robot plugin — it's fleet-level infrastructure).

#### 1a. Data Models (`src/auction/models.py`)

```python
@dataclass
class TaskSpec:
    # Fields match robot_submit_bid tool input (what the marketplace sends)
    task_description: str           # Human-readable
    task_category: str              # v1: "env_sensing" (sensor) or "visual_inspection" (camera)
    budget_ceiling: float           # Max the buyer pays, in USD
    sla_seconds: int                # Deadline in seconds
    capability_requirements: dict   # e.g. {"sensors_required": ["temperature", "humidity"]}
    requester_id: str               # Who's asking

@dataclass
class Bid:
    # Fields match robot_submit_bid tool output
    robot_name: str
    willing_to_bid: bool
    price: float                    # USD
    currency: str                   # "usd" or "usdc"
    sla_commitment_seconds: int
    confidence: float               # 0.0–1.0
    capabilities_offered: list[str]
    notes: str
    reason: str                     # populated if willing_to_bid=False

@dataclass
class AuctionResult:
    task: TaskSpec
    bids: list[Bid]
    winning_bid: Bid | None
    status: str                     # "bidding", "accepted", "paid", "executing", "completed", "failed"
    payment_method: str | None      # "usdc" or "stripe"
    stripe_checkout_url: str | None
    execution_result: dict | None
    delivery_ipfs_cid: str | None   # set after marketplace uploads delivery_data to IPFS
```

**Note on `task_category` vs v1 task types:** Our v1 types (`sensor_reading`, `camera`) map to marketplace categories as follows — `sensor_reading` → `"env_sensing"`, `camera` → `"visual_inspection"`. The `robot_submit_bid` tool receives marketplace categories; `plugin.bid()` handles the translation internally.

#### 1b. Engine (`src/auction/engine.py`)

```python
class AuctionEngine:
    def __init__(self, plugins: dict[str, RobotPlugin]):
        self.plugins = plugins
        self.auctions: dict[str, AuctionResult] = {}  # auction_id → result

    async def request_bids(self, task: TaskSpec) -> AuctionResult:
        """Fan out bid requests to all plugins, collect responses."""
        ...

    async def accept_bid(self, auction_id: str, robot_name: str) -> AuctionResult:
        """Accept a specific bid. Creates Stripe checkout if payment required."""
        ...

    async def execute(self, auction_id: str) -> dict:
        """Execute the accepted task on the winning robot."""
        ...
```

Key behaviors:
- `request_bids` calls `plugin.bid(task_spec)` on every registered plugin in parallel
- Each plugin's `bid()` checks its own capabilities and `bidding_terms` (see Stage 3) to decide whether to bid and at what price
- Plugins return `None` to decline (backward-compatible with the existing stub)
- Engine filters out bids below the robot's minimum price or above the client's budget

#### 1c. MCP Tools (`src/auction/mcp_tools.py`)

Register these on the fleet server (the import path `auction.mcp_tools` is already expected in `server.py`):

| Tool Name | Description |
|-----------|-------------|
| `fleet_request_bids` | Post a task, get bids from all capable robots |
| `fleet_list_auctions` | List active/recent auctions and their status |
| `fleet_accept_bid` | Accept a bid (triggers payment flow if Stripe configured) |
| `fleet_execute_task` | Execute the accepted task (after payment or approval) |
| `fleet_get_auction_status` | Check status of a specific auction |

### Stage 1d. Robot-Side MCP Tools (per-robot server)

The external marketplace calls these directly on each robot's MCP endpoint (`/{robot}/mcp`). Register them in each plugin's `register_tools()` via a shared helper in `src/core/marketplace_tools.py`:

#### `robot_submit_bid`

```python
@mcp.tool
async def robot_submit_bid(
    task_description: str,
    task_category: str,
    budget_ceiling: float,
    sla_seconds: int,
    capability_requirements: dict,
) -> dict:
    """Evaluate a task and return a bid or decline."""
    task_spec = {
        "task_description": task_description,
        "task_category": task_category,
        "budget_ceiling": budget_ceiling,
        "sla_seconds": sla_seconds,
        "capability_requirements": capability_requirements,
    }
    result = await plugin.bid(task_spec)
    if result is None:
        return {"willing_to_bid": False, "reason": "Task not supported or robot unavailable."}
    # Construct response from known fields to ensure schema compliance
    return {
        "willing_to_bid": True,
        "price": result.get("price", 0),
        "currency": result.get("currency", "usd"),
        "sla_commitment_seconds": result.get("sla_commitment_seconds", 0),
        "confidence": result.get("confidence", 0.5),
        "capabilities_offered": result.get("capabilities_offered", []),
        "notes": result.get("notes", ""),
    }
```

#### `robot_execute_task`

```python
@mcp.tool
async def robot_execute_task(
    task_id: str,
    task_description: str,
    parameters: dict,
) -> dict:
    """Execute an accepted task. Returns delivery_data for IPFS upload."""
    return await plugin.execute(task_id, task_description, parameters)
```

#### `robot_get_pricing`

```python
@mcp.tool
async def robot_get_pricing() -> dict:
    """Return this robot's pricing and availability."""
    terms = plugin.metadata().bidding_terms
    return {
        "min_task_price_usd": (terms.min_price_cents / 100) if terms else 0.50,
        "rate_per_minute_usd": (terms.rate_per_minute_cents / 100) if terms and terms.rate_per_minute_cents else 0.10,
        "accepted_currencies": ["usd", "usdc"],
        "max_concurrent_tasks": terms.max_concurrent_tasks if terms else 1,
        "task_categories": terms.accepted_task_types if terms else [],
        "availability": "online",  # plugins can override to check liveness
    }
```

These three tools are added to each plugin's `tool_names()` list and registered alongside existing tools like `tumbller_move`.

### Stage 2: Plugin Bid Implementations

Override `bid()` in each robot plugin to return real bids based on capabilities.

#### 2a. Tumbller (`src/robots/tumbller/__init__.py`)

```python
async def bid(self, task_spec: dict) -> dict | None:
    # Tumbller handles env_sensing (has temp/humidity sensor)
    # "sensor_reading" is our internal name; marketplace sends "env_sensing"
    if task_spec.get("task_category") not in ("env_sensing", "sensor_reading"):
        return None

    # Capability check — if the buyer specified required sensors, verify we have them
    reqs = task_spec.get("capability_requirements") or {}
    required_sensors = set(reqs.get("sensors_required", []))
    if required_sensors and not required_sensors.issubset({"temperature", "humidity"}):
        return None  # buyer needs sensors we don't have

    # Budget check
    terms = self.metadata().bidding_terms
    min_price = (terms.min_price_cents / 100) if terms else 0.50
    if task_spec.get("budget_ceiling", 0) < min_price:
        return None

    # Liveness check — reuse long-lived client or create and close a temp one
    client = getattr(self, "client", None)
    if client is None:
        from .client import TumbllerClient
        client = TumbllerClient()
        try:
            await client.get("/info")
        except Exception:
            await client.aclose()
            return None  # offline, can't bid
        await client.aclose()
    else:
        try:
            await client.get("/info")
        except Exception:
            return None

    return {
        "price": min_price,
        "currency": "usd",
        "sla_commitment_seconds": 30,
        "confidence": 0.95,
        "capabilities_offered": ["temperature", "humidity"],
        "notes": "SHT3x sensor, accuracy ±0.3°C / ±2% RH.",
    }
```

#### 2b. FakeRover (`src/robots/fakerover/__init__.py`)

`bid()` is **already implemented** in `src/robots/fakerover/__init__.py`. It:
- Reuses `self.client` if `register_tools()` was called, otherwise creates a temporary one
- Checks liveness (`/info`) and sensor availability (`/sensor/ht`)
- Filters on `task_spec["capability_requirements"]["sensors_required"]`
- Returns a rich bid dict including `price` (string), `sla_commitment_seconds`, `ai_confidence`, and `capability_metadata`

Stage 2b work is: align the existing `bid()` return to the Bid dataclass schema and add `bidding_terms` to `FakeRoverPlugin.metadata()`. Specific field renames needed:

| Current (FakeRover) | Target (Bid schema) |
|---------------------|---------------------|
| `price` (string, e.g. `"0.50"`) | `price` (float, e.g. `0.50`) |
| `ai_confidence` | `confidence` |
| `capability_metadata` (nested dict) | `capabilities_offered` (flat list of strings) |
| *(missing)* | `currency` (`"usd"`) |
| *(missing)* | `notes` (string) |

#### 2c. Tello

Bids on `camera` tasks (has a camera). Declines `sensor_reading` tasks.

### Stage 3: Bidding Terms in On-Chain Metadata

Extend the robot's on-chain registration to include bidding terms. These are stored as ERC-8004 metadata keys so any client can read them before even connecting to the MCP server.

#### 3a. Extend `RobotMetadata` dataclass

Add an optional `bidding_terms` field to `RobotMetadata`:

```python
@dataclass
class BiddingTerms:
    min_price_cents: int = 50       # Floor price (e.g. 50 = $0.50)
    rate_per_minute_cents: int | None = 10  # Per-minute rate (e.g. 10 = $0.10); None = flat price only
    currency: str = "usd"
    accepted_task_types: list[str] = field(default_factory=list)  # v1: "sensor_reading", "camera"
    max_duration_secs: int = 300    # Longest task the robot will accept
    max_concurrent_tasks: int = 1   # How many tasks this robot can run simultaneously
    requires_approval: bool = True  # Whether fleet operator must approve before execution

@dataclass
class RobotMetadata:
    # ... existing fields ...
    bidding_terms: BiddingTerms | None = None  # None = not participating in marketplace
```

#### 3b. Update `registration.py`

Write bidding terms as on-chain metadata using the keys the marketplace reads during discovery:

```
min_bid_price         → "50"              # cents (USD), matches getAgentWallet pattern
accepted_currencies   → "usd,usdc"        # comma-separated
task_categories       → "env_sensing"     # comma-separated marketplace category names
```

**Mapping:** `BiddingTerms.accepted_task_types` (`["sensor_reading", "camera"]`) is translated to marketplace categories (`"env_sensing,visual_inspection"`) before writing on-chain.

#### 3c. Update `discovery.py`

When discovering robots, read and return bidding metadata so clients know what robots accept before posting a task.

Add to discovery result:
```json
{
  "bidding_terms": {
    "min_bid_price": 50,
    "accepted_currencies": ["usd", "usdc"],
    "task_categories": ["env_sensing"]
  }
}
```

### Stage 4: Payment Integration

#### Payment paths

| Method | Default | Split | Setup required |
|--------|---------|-------|----------------|
| USDC (on-chain) | Yes | 88% to robot wallet, 12% platform | None — wallet already set via `setAgentWallet()` |
| Stripe card | Optional | 88% to Stripe Connect Express account, 12% platform | Complete Stripe onboarding (KYC) |

USDC flows directly to the wallet registered on-chain (`getAgentWallet(agentId)`). No code changes needed for this path — the marketplace handles it. Robot operators just need their wallet set.

#### Stage 4a: Stripe Payment Integration (optional card path)

#### 4a. New module: `src/auction/payments.py`

```python
import stripe  # pip install stripe

class StripePaymentHandler:
    def __init__(self, api_key: str, webhook_secret: str, base_url: str):
        stripe.api_key = api_key          # module-level — used throughout
        self.webhook_secret = webhook_secret
        self.base_url = base_url          # e.g. "https://<ngrok-domain>" from NGROK_DOMAIN env var

    def create_checkout_session(self, auction_id: str, auction: AuctionResult) -> str:
        """Create a Stripe Checkout session for the accepted bid.
        Returns the checkout URL."""
        session = stripe.checkout.Session.create(
            payment_method_types=["card"],
            line_items=[{
                "price_data": {
                    "currency": "usd",
                    "unit_amount": auction.winning_bid.price_cents,
                    "product_data": {
                        "name": f"Robot Task: {auction.task.description}",
                        "description": f"Executed by {auction.winning_bid.robot_name}",
                    },
                },
                "quantity": 1,
            }],
            mode="payment",
            success_url=f"{self.base_url}/auction/{auction_id}/success",
            cancel_url=f"{self.base_url}/auction/{auction_id}/cancel",
            metadata={"auction_id": auction_id},
        )
        return session.url

    async def handle_webhook(self, payload: bytes, sig_header: str) -> str | None:
        """Verify and process a Stripe webhook event.
        Returns auction_id if payment succeeded, None otherwise."""
        event = stripe.Webhook.construct_event(payload, sig_header, self.webhook_secret)
        if event["type"] == "checkout.session.completed":
            return event["data"]["object"]["metadata"]["auction_id"]
        return None
```

#### 4b. Stripe Connect Express (receiving card payments)

- Fleet operator creates a **Stripe Connect Express** account (not Standard — Express is what the marketplace onboards operators onto)
- The marketplace platform sends the operator an onboarding link; operator completes KYC (~5 min)
- Operator shares their `acct_...` ID with the marketplace
- Checkout sessions use "destination charges" — buyer pays via Checkout, 88% routed to robot's Express account, 12% retained by platform
- `STRIPE_SECRET_KEY` and `STRIPE_WEBHOOK_SECRET` go in `.env` for the platform side
- `STRIPE_CONNECT_ACCOUNT_ID` — operator's `acct_...` ID, stored in `.env`

#### 4c. FastAPI webhook endpoint

Add to the gateway (`server.py` or a new `src/auction/webhooks.py`):

```python
@app.post("/stripe/webhook")
async def stripe_webhook(request: Request):
    """Handle Stripe payment confirmation.
    On success, mark auction as 'paid' and trigger task execution."""
    ...
```

#### 4d. Environment variables

```
STRIPE_SECRET_KEY            — Stripe API secret key (platform)
STRIPE_WEBHOOK_SECRET        — Webhook endpoint signing secret
STRIPE_CONNECT_ACCOUNT_ID    — Operator's acct_... ID from Stripe Connect Express onboarding
```

Add `stripe` to `pyproject.toml` dependencies (optional extra: `marketplace`). USDC path requires no additional dependencies.

### Stage 5: Approval Flow

Two modes for task execution:

#### Mode A: Human-in-the-Loop (default)
1. Client posts task → robots bid → client accepts bid
2. Stripe checkout → payment confirmed
3. Fleet operator gets notification (MCP tool response, webhook, etc.)
4. Operator calls `fleet_execute_task` to approve and trigger execution
5. Robot executes → result returned

#### Mode B: Autonomous
1. Robot's `bidding_terms.requires_approval = False`
2. After payment confirmation, execution happens automatically
3. Result is stored and queryable via `fleet_get_auction_status`

The `requires_approval` flag is set per-robot in `BiddingTerms` and stored on-chain so clients know upfront.

### Stage 5b: Delivery Format

The `robot_execute_task` tool must return this structure. The marketplace wraps it in a delivery envelope and uploads to IPFS; the robot returns only `delivery_data`.

```python
# Minimum required fields in execute() return value:
{
    "success": True,
    "delivery_data": {
        "readings": [...],          # sensor data or image references
        "summary": "...",           # human-readable summary
        "robot_id": "989",          # ERC-8004 agent ID integer
        "robot_name": "Tumbller Self-Balancing Robot",
        "duration_seconds": 30,
    }
}

# On failure:
{
    "success": False,
    "error": "Reason for failure.",
    "partial_data": {...},          # whatever was collected before failure
}
```

The marketplace wraps this in:
```json
{
  "schema": "yak-robotics/delivery/v1",
  "request_id": "...",
  "robot_id": "989",
  "delivered_at": "2026-04-02T10:30:00Z",
  "data": { "...delivery_data from robot..." }
}
```

The robot does **not** do the IPFS upload — the marketplace handles it. The robot just returns clean JSON.

### Stage 5c: Feedback Tool

After delivering results, robots (or the fleet server on their behalf) should submit feedback via the marketplace's `auction_submit_feedback` tool. This affects the robot's reputation score (15% weight in bid scoring).

```python
# Called after successful task delivery:
await marketplace_mcp.call_tool("auction_submit_feedback", {
    "request_id": task_id,
    "role": "operator",
    "rating": 5,
    "comment": "Completed within SLA. All sensor readings nominal.",
    "robot_id": agent_id,
})
```

The marketplace returns:
```json
{"recorded": true, "request_id": "...", "rating": 5}
```

This is optional for v1 but should be wired in once the marketplace MCP endpoint is reachable from the fleet server.

### Stage 6: Multi-Chain Registration

Currently the chain ID is hardcoded to `11155111` (Ethereum Sepolia) in `registration.py` and `discovery.py`. This stage adds a `--chain` flag so operators can register and discover robots on any supported chain.

#### Supported Chains

| Name | Chain ID | RPC Default |
|------|----------|-------------|
| `eth-sepolia` | `11155111` | `https://ethereum-sepolia-rpc.publicnode.com` |
| `eth-mainnet` | `1` | `https://ethereum-rpc.publicnode.com` |
| `base-sepolia` | `84532` | `https://sepolia.base.org` |
| `base-mainnet` | `8453` | `https://mainnet.base.org` |

#### 6a. Chain config map (`src/core/chains.py`)

```python
CHAINS = {
    "eth-sepolia":  {"chain_id": 11155111, "rpc": "https://ethereum-sepolia-rpc.publicnode.com"},
    "eth-mainnet":  {"chain_id": 1,        "rpc": "https://ethereum-rpc.publicnode.com"},
    "base-sepolia": {"chain_id": 84532,    "rpc": "https://sepolia.base.org"},
    "base-mainnet": {"chain_id": 8453,     "rpc": "https://mainnet.base.org"},
}
DEFAULT_CHAIN = "eth-sepolia"

def get_chain(name: str | None = None) -> dict:
    """Return chain config by name. Falls back to DEFAULT_CHAIN."""
    return CHAINS[name or DEFAULT_CHAIN]
```

Single source of truth. Every module that needs a chain ID imports from here.

#### 6b. Update `registration.py`

- `_make_sdk()` accepts an optional `chain: str` parameter
- Resolves chain ID and default RPC from `chains.py`
- `RPC_URL` from `.env` **overrides** the default RPC for the selected chain (power users)
- `register_robot()` and `update_robot()` accept `chain: str | None`

#### 6c. Update `discovery.py`

- `_get_sdk()` accepts an optional `chain: str` parameter
- `discover_robots()` accepts `chain: str | None`
- Default remains `eth-sepolia` for backward compatibility

#### 6d. Update CLI scripts

All scripts get a `--chain` flag:

```bash
# Register on Base mainnet
uv run python scripts/register.py tumbller --chain base-mainnet

# Discover on Base Sepolia
uv run python scripts/discover.py --provider yakrover --chain base-sepolia

# Update agent on Eth mainnet
uv run python scripts/update_agent.py 1:42 --chain eth-mainnet

# Fix metadata on Base
uv run python scripts/fix_metadata.py tumbller 42 --chain base-mainnet
```

Default is `eth-sepolia` (no breaking change — existing commands work as before).

#### 6e. Environment variable: `CHAIN`

Optional. If set in `.env`, it becomes the default chain for all commands (overridden by `--chain` flag):

```
CHAIN=base-mainnet    # All commands default to Base mainnet
RPC_URL=https://...   # Still overrides the default RPC for whatever chain is selected
```

#### 6f. Discovery MCP tool

The `discover_robot_agents` MCP tool gets an optional `chain` parameter so LLMs can search across chains:

```python
@mcp.tool
async def discover_robot_agents(
    robot_type: str | None = None,
    fleet_provider: str | None = None,
    chain: str | None = None,  # NEW — defaults to env CHAIN or eth-sepolia
) -> dict:
```

#### What this does NOT do (out of scope)

- Cross-chain discovery (searching all chains at once) — post one query per chain
- Chain-specific wallet management — same `SIGNER_PVT_KEY` works on all EVM chains
- Bridge or cross-chain messaging — each chain is independent

---

## New Files Summary

```
src/
├── core/
│   └── chains.py         # Chain config map (chain ID, default RPC per network)
├── auction/
│   ├── __init__.py
│   ├── models.py         # TaskSpec, Bid, AuctionResult dataclasses
│   ├── engine.py         # AuctionEngine — bid fanout, acceptance, execution
│   ├── mcp_tools.py      # MCP tool registration (fleet_request_bids, etc.)
│   ├── payments.py       # Stripe checkout + webhook handling
│   └── webhooks.py       # FastAPI route for /stripe/webhook
```

## Modified Files Summary

| File | Changes |
|------|---------|
| `src/core/plugin.py` | Add `BiddingTerms` dataclass, `execute()` abstract method, field to `RobotMetadata` |
| `src/core/marketplace_tools.py` | Shared helper to register `robot_submit_bid`, `robot_execute_task`, `robot_get_pricing` on any robot MCP server |
| `src/core/server.py` | Call `marketplace_tools` in `create_robot_server()`; instantiate `AuctionEngine`; mount webhook route |
| `src/core/registration.py` | Write bidding terms as on-chain metadata keys (`min_bid_price`, `accepted_currencies`, `task_categories`); accept `chain` param |
| `src/core/discovery.py` | Read and return bidding terms in discovery results; accept `chain` param |
| `src/robots/tumbller/__init__.py` | Override `bid()` and `execute()`, set `bidding_terms` in metadata |
| `src/robots/fakerover/__init__.py` | Align existing `bid()` to new schema, add `execute()`, set `bidding_terms` in metadata |
| `src/robots/tello/__init__.py` | Override `bid()` and `execute()` for camera tasks |
| `pyproject.toml` | Add `stripe` dependency, `marketplace` optional extra |
| `scripts/register.py` | Add `--chain` flag |
| `scripts/discover.py` | Add `--chain` flag |
| `scripts/update_agent.py` | Add `--chain` flag |
| `scripts/fix_metadata.py` | Add `--chain` flag |
| `.env` (template) | Add `STRIPE_SECRET_KEY`, `STRIPE_WEBHOOK_SECRET`, `STRIPE_CONNECT_ACCOUNT_ID`, `CHAIN` |

---

## Implementation Order

1. **Stage 6** — Multi-chain support (small, self-contained, unblocks Base registration immediately)
2. **Stage 1a+1b** — Models + Engine core
3. **Stage 1d** — Robot-side MCP tools (`robot_submit_bid`, `robot_execute_task`, `robot_get_pricing`) — this is what the external marketplace actually calls; highest priority after models
4. **Stage 2b** — Align FakeRover bid/execute to new schema; test full bid+execute flow without hardware
5. **Stage 1c** — Fleet server auction tools (LLM-facing orchestration layer)
6. **Stage 3** — On-chain bidding terms (`min_bid_price`, `accepted_currencies`, `task_categories`)
7. **Stage 5b** — Delivery format (standardise `execute()` return across all plugins)
8. **Stage 2a+2c** — Tumbller + Tello bid/execute implementations
9. **Stage 4** — Payment integration: USDC path is free (wallet already exists); Stripe Connect Express last
10. **Stage 5** — Approval flow refinement
11. **Stage 5c** — Feedback tool (lowest priority, marketplace must be reachable first)

---

## Design Decisions

1. **Task taxonomy** — Two task types in v1: `sensor_reading` and `camera`. Freeform strings (no enum), so more can be added later without changing the engine. The robot's `bid()` decides if it can handle the `task_type`. The `accepted_task_types` in bidding terms is a hint list for clients, not a constraint enforced by the engine.

2. **Pricing model** — Fixed price per robot, set in `BiddingTerms.min_price_cents`. That's the price. The `bid()` method returns it directly. Dynamic pricing (battery, distance, complexity) can be added later inside `bid()` without changing the engine.

3. **Multi-bid acceptance** — No. One task, one winning robot. If a client wants multiple robots, they post multiple tasks. No coordination logic needed.

4. **Escrow vs. direct payment** — Direct charge on acceptance. No escrow. Stripe Checkout charges immediately. Escrow (hold/capture/release, disputes) is out of scope for v1.

5. **Failure handling** — Log the failure, mark the auction as `"failed"`. No automatic refund. The fleet operator can issue manual refunds via the Stripe dashboard. Automate later if needed.

6. **Rate limiting** — One task at a time per robot. If a robot is currently executing, its `bid()` returns `None`. Tracked via a `busy: set[str]` (robot names) on the engine. No concurrency infrastructure.
