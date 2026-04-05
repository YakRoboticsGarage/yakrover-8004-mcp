# yakrover-8004-mcp

Modular MCP framework for multi-robot fleet control, on-chain discovery via [ERC-8004](https://eips.ethereum.org/EIPS/eip-8004), and a robot-side bidding marketplace — robots receive task requests, generate bids, execute paid work, and receive payment in USDC or via Stripe.

A plugin-based architecture that consolidates shared infrastructure so any robot can be added with minimal glue code. Each robot gets its own isolated MCP server, all served behind a single port and ngrok tunnel.

## Architecture

```
┌────────────────────────────────────────────────────────────────────────────┐
│         External Marketplace                  LLM / AI Agent               │
│       (yakrover-marketplace)            (Claude, GPT, etc. via MCP)        │
└──────┬─────────────────────────────────────────┬──────────────────────┬────┘
       │ robot_submit_bid                         │                      │
       │ robot_execute_task   /fleet/mcp ─────────┘          /tello/mcp │
       │ robot_get_pricing    fleet_request_bids                         │
       │                      fleet_accept_bid          /tumbller/mcp ──┘
       │                      fleet_execute_task
       │                      fleet_get_auction_status
       │                      discover_robot_agents
       │
       └──────────────────────────────┐
                                      │
                              ┌───────▼────────┐
                              │  ngrok tunnel   │
                              │ single URL      │
                              │ single port     │
                              └───────┬─────────┘
                                      │
┌─────────────────────────────────────▼──────────────────────────────────────┐
│                          FastAPI Gateway  :8000                              │
│                                                                              │
│ ┌──────────────────────────┐  ┌────────────────────┐  ┌──────────────────┐ │
│ │       /fleet/mcp         │  │   /tumbller/mcp    │  │   /tello/mcp     │ │
│ │   Fleet MCP Server       │  │   Tumbller MCP     │  │   Tello MCP      │ │
│ │                          │  │                    │  │                  │ │
│ │  discover_robot_agents   │  │  tumbller_move     │  │  tello_takeoff   │ │
│ │  fleet_request_bids      │  │  tumbller_is       │  │  tello_land      │ │
│ │  fleet_list_auctions     │  │    _online         │  │  tello_move      │ │
│ │  fleet_accept_bid        │  │  tumbller_get      │  │  tello_rotate    │ │
│ │  fleet_execute_task      │  │    _temperature    │  │  tello_flip      │ │
│ │  fleet_get_auction_status│  │    _humidity       │  │  tello_get_*     │ │
│ │                          │  │                    │  │                  │ │
│ │  ┌───────────────────┐   │  │  robot_submit_bid  │  │  robot_submit    │ │
│ │  │  AuctionEngine    │   │  │  robot_execute     │  │    _bid          │ │
│ │  │  bid fan-out      │   │  │    _task           │  │  robot_execute   │ │
│ │  │  accept / execute │   │  │  robot_get_pricing │  │    _task         │ │
│ │  │  requires_approval│   │  │                    │  │  robot_get       │ │
│ │  └───────────────────┘   │  └────────┬───────────┘  │    _pricing      │ │
│ └──────────────────────────┘           │               └────────┬─────────┘ │
│                                        │                        │            │
│  POST /stripe/webhook                  │                        │            │
│  → verify sig → on_payment_confirmed() │                        │            │
│    Mode A: status="paid", wait         │                        │            │
│    Mode B: auto-execute via task       │                        │            │
│                                        │                        │            │
└────────────────────────────────────────┼────────────────────────┼────────────┘
                                         │                        │
                             ┌───────────▼──────┐    ┌───────────▼────────┐
                             │ TumbllerClient   │    │   TelloClient      │
                             │ (HTTP/httpx)     │    │   (UDP/djitellopy) │
                             └───────┬──────────┘    └─────────┬──────────┘
                                     │                          │
                            HTTP :80 │                UDP :8889 │
                                     ▼                          ▼
                             ┌───────────────┐       ┌──────────────────┐
                             │  ESP32-S3     │       │  DJI Tello       │
                             │  Tumbller     │       │  Drone           │
                             └───────────────┘       └──────────────────┘

Payment paths
  USDC  ──► buyer pays robot on-chain wallet (getAgentWallet) — 88% to robot
  Card  ──► Stripe Checkout ──► POST /stripe/webhook ──► on_payment_confirmed()
            88% routed to operator Stripe Connect Express, 12% platform fee

On-chain
  ERC-8004 registry (Ethereum Sepolia / Base / …)
  └── robot agent card on IPFS: endpoint, tools, bidding_terms
```

## Bidding Marketplace

The external [yakrover-marketplace](https://github.com/YakRoboticsGarage/yakrover-marketplace) orchestrates auctions. This repo implements the **robot side**: bid evaluation, task execution, payment receipt, and on-chain bidding terms.

### Full lifecycle

```
1. DISCOVER   Robot registered on ERC-8004. Marketplace finds it, reads
              bidding_terms (min_price, accepted_task_types) from IPFS agent card.

2. BID        Buyer posts task → marketplace calls robot_submit_bid on each
              robot's /mcp endpoint → robot evaluates capability + liveness
              → returns price or declines.

3. AWARD      Buyer picks winner. Robot is notified via task acceptance.

4. EXECUTE    Marketplace (or fleet operator) calls robot_execute_task → robot
              does the work → returns delivery_data JSON.

5. DELIVER    Marketplace wraps delivery_data in the yakrover/delivery/v1
              envelope and uploads to IPFS.

6. VERIFY     Buyer reviews sensor data / images via the IPFS link.

7. PAY        Buyer releases payment:
              USDC → robot on-chain wallet (88%)
              Card → Stripe Checkout → /stripe/webhook (88% to Connect Express)
```

### Robot-side MCP tools (on every robot's /mcp endpoint)

| Tool | Called by | Description |
|------|-----------|-------------|
| `robot_submit_bid` | Marketplace | Evaluate a task and return a bid or decline |
| `robot_execute_task` | Marketplace or fleet | Execute an accepted task; return delivery_data |
| `robot_get_pricing` | Anyone | Return this robot's pricing and availability |

### Fleet MCP tools (on /fleet/mcp, for LLM clients)

| Tool | Description |
|------|-------------|
| `fleet_request_bids` | Post a task to all capable robots, collect bids in parallel |
| `fleet_list_auctions` | List active/recent auctions and their status |
| `fleet_accept_bid` | Accept a specific robot's bid; creates Stripe checkout if configured |
| `fleet_execute_task` | Execute the accepted task (operator approval in Mode A) |
| `fleet_get_auction_status` | Full auction state including execution result |

### Approval flow

**Mode A — Human-in-the-loop** (`requires_approval=True`, default):
1. Task posted → robots bid → bid accepted
2. Stripe Checkout created → buyer pays
3. Webhook fires → auction advances to `"paid"`
4. Fleet operator calls `fleet_execute_task` to approve
5. Robot executes → delivery_data returned

**Mode B — Autonomous** (`requires_approval=False` in `BiddingTerms`):
1–3 same as Mode A
4. Webhook fires → `on_payment_confirmed()` schedules execution automatically
5. Robot executes → result stored; query via `fleet_get_auction_status`

Set `requires_approval` per-robot in `BiddingTerms` inside the plugin's `metadata()`.

### Delivery format

`robot_execute_task` always returns:

```json
{
  "success": true,
  "delivery_data": {
    "readings": [{"type": "temperature", "value": 21.3, "unit": "celsius"}],
    "summary": "Temperature: 21.3°C, Humidity: 58%",
    "robot_id": "989",
    "robot_name": "Tumbller Self-Balancing Robot",
    "duration_seconds": 1.2
  }
}
```

On failure:

```json
{"success": false, "error": "Reason.", "partial_data": {}}
```

The marketplace wraps `delivery_data` in a `yakrover/delivery/v1` envelope and uploads to IPFS — the robot never does the IPFS upload itself.

### On-chain bidding terms

Each plugin's `BiddingTerms` are serialised into the IPFS agent card at registration time as flat string fields:

```json
{
  "metadata": {
    "min_bid_price": "50",
    "accepted_currencies": "usd,usdc",
    "task_categories": "env_sensing"
  }
}
```

Update them by changing `BiddingTerms` in the plugin and running:

```bash
uv run python scripts/update_agent.py tumbller 11155111:989
```

## Prerequisites

- Python 3.13+
- [uv](https://docs.astral.sh/uv/) package manager
- [ngrok](https://ngrok.com/) account (free tier) for public tunnel
- Sepolia ETH for on-chain registration (free from a [faucet](https://www.alchemy.com/faucets/ethereum-sepolia))
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
# Fill in NGROK_AUTHTOKEN, NGROK_DOMAIN, SIGNER_PVT_KEY, PINATA_JWT
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

Then ask Claude to move the fake rover, read its temperature, or post a bid.

## Install Options

```bash
uv sync                          # Core only (discovery + registration)
uv sync --extra fakerover        # With fake rover (no hardware needed)
uv sync --extra tumbller         # With Tumbller robot support
uv sync --extra tello            # With Tello drone support
uv sync --extra marketplace      # Stripe payment integration
uv sync --extra all              # Everything
```

## Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `NGROK_AUTHTOKEN` | Yes (tunnel) | ngrok auth token |
| `NGROK_DOMAIN` | Yes (tunnel) | ngrok static domain (e.g. `foo.ngrok-free.dev`) |
| `SIGNER_PVT_KEY` | Yes (on-chain) | Wallet private key for ERC-8004 transactions |
| `PINATA_JWT` | Yes (on-chain) | Pinata API token for IPFS uploads |
| `MCP_BEARER_TOKEN` | Optional | Bearer token for MCP auth |
| `RPC_URL` | Optional | Override default chain RPC URL |
| `CHAIN` | Optional | Default chain (`eth-sepolia`, `base-mainnet`, etc.) |
| `STRIPE_SECRET_KEY` | Optional | Stripe API secret key (card payments) |
| `STRIPE_WEBHOOK_SECRET` | Optional | Stripe webhook signing secret |
| `STRIPE_CONNECT_ACCOUNT_ID` | Optional | Operator's `acct_...` ID from Stripe Connect Express |
| `TUMBLLER_URL` | Optional | Tumbller address (default: `http://finland-tumbller-01.local`) |
| `TELLO_HOST` | Optional | Tello drone IP (default: `192.168.10.1`) |
| `FAKEROVER_URL` | Optional | Fake rover address (default: `http://localhost:8080`) |

`STRIPE_SECRET_KEY` and `STRIPE_WEBHOOK_SECRET` must both be set to activate Stripe. `NGROK_DOMAIN` must also be set (Stripe requires absolute redirect URLs). Without Stripe, the USDC on-chain path works with no extra setup.

## Multi-Chain Support

All CLI scripts and the `discover_robot_agents` MCP tool accept a `--chain` flag:

| Name | Chain ID |
|------|----------|
| `eth-sepolia` | 11155111 (default) |
| `eth-mainnet` | 1 |
| `base-sepolia` | 84532 |
| `base-mainnet` | 8453 |

```bash
uv run python scripts/register.py tumbller --chain base-mainnet
uv run python scripts/discover.py --provider yakrover --chain base-sepolia
```

Set `CHAIN=base-mainnet` in `.env` to change the default for all commands.

## Discovery Flow

Robots are registered on an EVM blockchain via [ERC-8004](https://eips.ethereum.org/EIPS/eip-8004) — discoverable by anyone, anywhere, with no central directory.

### Register (fleet operator, one-time)

```bash
# Start the gateway
uv run python scripts/serve.py --robots tumbller --ngrok

# Register on Ethereum Sepolia
uv run python scripts/register.py tumbller
```

Writes to the blockchain:
- MCP endpoint → `https://your-domain.ngrok.app/tumbller/mcp`
- Fleet endpoint → `https://your-domain.ngrok.app/fleet/mcp`
- Tools → `["tumbller_move", ..., "robot_submit_bid", "robot_execute_task", "robot_get_pricing"]`
- Bidding terms → `min_bid_price=50`, `accepted_currencies=usd,usdc`, `task_categories=env_sensing`

### Discover (anyone)

```bash
uv run python scripts/discover.py --provider yakrover

# Write discovered endpoints into Claude MCP config
uv run python scripts/discover.py --add-mcp            # → .mcp.json (project)
uv run python scripts/discover.py --add-mcp --scope global  # → ~/.claude.json
```

Or via LLM at runtime:

```
User: "Find robots that can read temperature"
LLM:  calls discover_robot_agents(fleet_provider="yakrover") on /fleet/mcp
  →   returns: Tumbller in Finland, min_bid_price=$0.50, task_categories=[env_sensing]
```

## Adding a Robot

Each robot is a plugin — a package under `src/robots/` with three files:

```
src/robots/myrobot/
├── __init__.py    # RobotPlugin subclass: metadata(), tool_names(), register_tools(),
│                  #   bid(), execute()
├── client.py      # Communication with the physical robot
└── tools.py       # MCP tool definitions
```

Implement `bid()` and `execute()` to opt into the bidding marketplace:

```python
async def bid(self, task_spec: dict) -> dict | None:
    # Return None to decline; return bid dict to participate
    ...

async def execute(self, task_id: str, task_description: str, parameters: dict) -> dict:
    # Return {"success": True, "delivery_data": {...}}
    ...
```

Set `bidding_terms` on `RobotMetadata` to publish pricing on-chain:

```python
def metadata(self) -> RobotMetadata:
    return RobotMetadata(
        ...,
        bidding_terms=BiddingTerms(
            min_price_cents=50,           # $0.50 minimum
            rate_per_minute_cents=10,     # $0.10/min
            accepted_task_types=["sensor_reading"],
            requires_approval=True,       # False = auto-execute after payment
        ),
    )
```

See `src/robots/_template/` for a copyable starting point and `docs/MODULAR_FRAMEWORK_PLAN.md` Section 7 for a step-by-step guide.

## Common Commands

```bash
# Serve robots
uv run python scripts/serve.py --ngrok                          # All robots
uv run python scripts/serve.py --robots tumbller --ngrok        # Single robot
uv run python scripts/serve.py --robots tumbller tello --ngrok  # Multi-select

# Fake rover (hardware-free development + bidding tests)
PYTHONPATH=src uv run python -m robots.fakerover.simulator       # Start simulator
uv run python scripts/serve.py --robots fakerover                # MCP gateway

# On-chain registration and management
uv run python scripts/register.py tumbller
uv run python scripts/register.py tumbller --chain base-mainnet
uv run python scripts/update_agent.py tumbller 11155111:989      # Update metadata
uv run python scripts/fix_metadata.py tumbller 989               # Fix on-chain KV keys

# Discovery
uv run python scripts/discover.py --provider yakrover
uv run python scripts/discover.py --add-mcp --provider yakrover

# Wallet
uv run python scripts/generate_wallet.py
```

## Project Structure

```
src/
  core/
    plugin.py              # RobotPlugin base class, RobotMetadata, BiddingTerms
    server.py              # FastAPI gateway, ASGI sub-mounts, Stripe webhook mount
    tunnel.py              # ngrok tunnel helper
    discovery.py           # discover_robot_agents MCP tool + CLI helper
    registration.py        # Generic ERC-8004 register/update/fix
    marketplace_tools.py   # Shared robot_submit_bid/execute_task/get_pricing registrar
    chains.py              # Multi-chain config (eth-sepolia, base-mainnet, etc.)
    wallet.py              # Ethereum wallet generation
  auction/
    models.py              # TaskSpec, Bid, AuctionResult dataclasses
    engine.py              # AuctionEngine — bid fan-out, accept, execute, approval flow
    mcp_tools.py           # Fleet MCP tools (fleet_request_bids, fleet_accept_bid, …)
    payments.py            # StripePaymentHandler — Checkout sessions + webhook verify
    webhooks.py            # FastAPI POST /stripe/webhook route
  robots/
    fakerover/             # Software-only simulator (no hardware needed)
    tumbller/              # ESP32-S3 self-balancing robot (HTTP/httpx)
    tello/                 # DJI Tello drone (UDP/djitellopy)
    _template/             # Copyable scaffolding for new robots
scripts/
  serve.py                 # Start MCP gateway for one or more robots
  register.py              # Register a robot on ERC-8004
  discover.py              # CLI discovery + MCP config writer (--add-mcp)
  update_agent.py          # Update on-chain agent metadata / bidding terms
  fix_metadata.py          # Fix flat on-chain KV keys
  generate_wallet.py       # Ethereum wallet generator
docs/
  BIDDING_MARKETPLACE_PLAN.md  # Full marketplace design
  MODULAR_FRAMEWORK_PLAN.md    # Framework design
  DEVELOPMENT.md               # Implementation progress tracker
  CHANGELOG.md                 # Version history
```

## Links

- [ERC-8004 Specification](https://eips.ethereum.org/EIPS/eip-8004)
- [8004scan Best Practices](https://best-practices.8004scan.io)
- [agent0-sdk](https://pypi.org/project/agent0-sdk/)
- [FastMCP](https://pypi.org/project/fastmcp/)
- [MCP Specification](https://spec.modelcontextprotocol.io)

## License

Apache 2.0 — see [LICENSE](LICENSE).
