# Robot Bidding Marketplace — Implementation Plan

## Overview

Add the ability for robots in the fleet to **receive task requests, generate bids (price quotes), and execute paid work** — with real money flowing through Stripe. An LLM client (or another agent) posts a task; robots bid; the client accepts a bid; the robot executes; payment settles.

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

```
Client (LLM / Agent)
  │
  ├─ POST task via MCP tool ──► Fleet Server (/fleet/mcp)
  │                                │
  │                          AuctionEngine
  │                           │         │
  │                     bid request   bid request
  │                           │         │
  │                     TumbllerPlugin  TelloPlugin
  │                      .bid()          .bid()
  │                           │         │
  │                      {price, ETA}   None (decline)
  │                           │
  │  ◄── bid results ─────────┘
  │
  ├─ accept_bid via MCP tool ──► AuctionEngine
  │                                │
  │                          Stripe checkout session
  │                                │
  │                          on payment success
  │                                │
  │                          robot executes task
  │                                │
  │  ◄── execution result ─────────┘
```

---

## Stages

### Stage 1: Auction Engine Core (`src/auction/`)

Create `src/auction/` as a new internal package (not a robot plugin — it's fleet-level infrastructure).

#### 1a. Data Models (`src/auction/models.py`)

```python
@dataclass
class TaskSpec:
    task_type: str              # e.g. "move_patrol", "sensor_reading", "photo_survey"
    description: str            # Human-readable task description
    parameters: dict            # Task-specific params (waypoints, duration, etc.)
    max_budget_cents: int       # Client's max willingness to pay, in cents
    requester_id: str           # Who's asking

@dataclass
class Bid:
    robot_name: str
    price_cents: int            # Robot's asking price
    estimated_duration_secs: int
    confidence: float           # 0.0–1.0, how likely the robot can complete this
    capabilities_match: list[str]  # Which of its tools apply to this task
    requires_approval: bool     # Does the fleet operator need to approve execution?

@dataclass
class AuctionResult:
    task: TaskSpec
    bids: list[Bid]
    winning_bid: Bid | None
    status: str                 # "bidding", "accepted", "paid", "executing", "completed", "failed"
    stripe_checkout_url: str | None
    execution_result: dict | None
```

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

### Stage 2: Plugin Bid Implementations

Override `bid()` in each robot plugin to return real bids based on capabilities.

#### 2a. Tumbller (`src/robots/tumbller/__init__.py`)

```python
async def bid(self, task_spec: dict) -> dict | None:
    # Tumbller can handle: sensor readings (has temp/humidity sensor)
    if task_spec.get("task_type") != "sensor_reading":
        return None  # decline — can't do this

    # Check if robot is online before bidding
    from .client import TumbllerClient
    client = TumbllerClient()
    try:
        await client.get("/info")
    except Exception:
        return None  # offline, can't bid

    return {
        "price_cents": max(self.bidding_terms.get("min_price_cents", 50), ...),
        "estimated_duration_secs": 10,
        "confidence": 0.95,
        "capabilities_match": ["tumbller_get_temperature_humidity"],
        "requires_approval": True,  # default: human-in-the-loop
    }
```

#### 2b. FakeRover (`src/robots/fakerover/__init__.py`)

Same pattern but always online (simulator). Accepts `sensor_reading` tasks. Good for testing the full bid flow without hardware.

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
    currency: str = "usd"
    accepted_task_types: list[str] = field(default_factory=list)  # v1: "sensor_reading", "camera"
    max_duration_secs: int = 300    # Longest task the robot will accept
    requires_approval: bool = True  # Whether fleet operator must approve before execution

@dataclass
class RobotMetadata:
    # ... existing fields ...
    bidding_terms: BiddingTerms | None = None  # None = not participating in marketplace
```

#### 3b. Update `registration.py`

When registering/updating, write bidding terms as on-chain metadata:

```
bidding_min_price_cents  → "50"
bidding_currency         → "usd"
bidding_task_types       → "sensor_reading" or "sensor_reading,camera"
bidding_max_duration     → "300"
bidding_requires_approval → "true"
```

#### 3c. Update `discovery.py`

When discovering robots, read and return bidding metadata so clients know what robots accept before posting a task.

Add to discovery result:
```json
{
  "bidding_terms": {
    "min_price_cents": 50,
    "currency": "usd",
    "accepted_task_types": ["sensor_reading"],
    "max_duration_secs": 300,
    "requires_approval": true
  }
}
```

### Stage 4: Stripe Payment Integration

#### 4a. New module: `src/auction/payments.py`

```python
class StripePaymentHandler:
    def __init__(self, api_key: str, webhook_secret: str):
        self.stripe = stripe
        stripe.api_key = api_key

    def create_checkout_session(self, auction: AuctionResult) -> str:
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
            success_url=f"{base_url}/auction/{auction_id}/success",
            cancel_url=f"{base_url}/auction/{auction_id}/cancel",
            metadata={"auction_id": auction_id},
        )
        return session.url

    async def handle_webhook(self, payload, sig_header) -> str | None:
        """Process Stripe webhook — returns auction_id if payment succeeded."""
        ...
```

#### 4b. Stripe Connect (receiving money)

For the robot fleet to **receive real money**, set up a Stripe Connect account:

- Fleet operator creates a **Stripe Standard account** (or Connect Express)
- `STRIPE_SECRET_KEY` and `STRIPE_WEBHOOK_SECRET` go in `.env`
- Checkout sessions are created with the fleet's Stripe account
- Future: per-robot Stripe Connect sub-accounts for multi-operator fleets

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
STRIPE_SECRET_KEY       — Stripe API secret key
STRIPE_WEBHOOK_SECRET   — Webhook endpoint signing secret
STRIPE_SUCCESS_URL      — (optional) Custom redirect after payment
```

Add `stripe` to `pyproject.toml` dependencies (optional extra: `marketplace`).

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
| `src/core/plugin.py` | Add `BiddingTerms` dataclass, add field to `RobotMetadata` |
| `src/core/server.py` | Instantiate `AuctionEngine`, pass to `create_fleet_server`, mount webhook route |
| `src/core/registration.py` | Write bidding terms as on-chain metadata keys; accept `chain` param |
| `src/core/discovery.py` | Read and return bidding terms in discovery results; accept `chain` param |
| `src/robots/tumbller/__init__.py` | Override `bid()`, set `bidding_terms` in metadata |
| `src/robots/fakerover/__init__.py` | Override `bid()`, set `bidding_terms` in metadata |
| `src/robots/tello/__init__.py` | Override `bid()` for aerial tasks |
| `pyproject.toml` | Add `stripe` dependency, `marketplace` optional extra |
| `scripts/register.py` | Add `--chain` flag |
| `scripts/discover.py` | Add `--chain` flag |
| `scripts/update_agent.py` | Add `--chain` flag |
| `scripts/fix_metadata.py` | Add `--chain` flag |
| `.env` (template) | Add `STRIPE_SECRET_KEY`, `STRIPE_WEBHOOK_SECRET`, `CHAIN` |

---

## Implementation Order

1. **Stage 6** — Multi-chain support (small, self-contained, unblocks Base registration immediately)
2. **Stage 1a+1b** — Models + Engine (no external deps, testable in isolation)
3. **Stage 2b** — FakeRover bid implementation (test without hardware)
4. **Stage 1c** — MCP tools (end-to-end bid flow works with fakerover)
5. **Stage 3** — On-chain bidding terms metadata
6. **Stage 2a+2c** — Tumbller + Tello bid implementations
7. **Stage 4** — Stripe integration (last, because everything else works without it)
8. **Stage 5** — Approval flow refinement

---

## Design Decisions

1. **Task taxonomy** — Two task types in v1: `sensor_reading` and `camera`. Freeform strings (no enum), so more can be added later without changing the engine. The robot's `bid()` decides if it can handle the `task_type`. The `accepted_task_types` in bidding terms is a hint list for clients, not a constraint enforced by the engine.

2. **Pricing model** — Fixed price per robot, set in `BiddingTerms.min_price_cents`. That's the price. The `bid()` method returns it directly. Dynamic pricing (battery, distance, complexity) can be added later inside `bid()` without changing the engine.

3. **Multi-bid acceptance** — No. One task, one winning robot. If a client wants multiple robots, they post multiple tasks. No coordination logic needed.

4. **Escrow vs. direct payment** — Direct charge on acceptance. No escrow. Stripe Checkout charges immediately. Escrow (hold/capture/release, disputes) is out of scope for v1.

5. **Failure handling** — Log the failure, mark the auction as `"failed"`. No automatic refund. The fleet operator can issue manual refunds via the Stripe dashboard. Automate later if needed.

6. **Rate limiting** — One task at a time per robot. If a robot is currently executing, its `bid()` returns `None`. Tracked via a `busy: set[str]` (robot names) on the engine. No concurrency infrastructure.
