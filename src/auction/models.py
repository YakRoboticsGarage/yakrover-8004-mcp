from dataclasses import dataclass, field


@dataclass
class TaskSpec:
    task_description: str
    task_category: str       # "env_sensing" | "visual_inspection" (marketplace categories)
    budget_ceiling: float    # Max the buyer pays, in USD
    sla_seconds: int         # Deadline in seconds
    capability_requirements: dict
    requester_id: str


@dataclass
class Bid:
    robot_name: str
    willing_to_bid: bool
    price: float             # USD
    currency: str            # "usd" | "usdc"
    sla_commitment_seconds: int
    confidence: float        # 0.0–1.0
    capabilities_offered: list[str]
    notes: str
    reason: str              # populated when willing_to_bid=False


@dataclass
class AuctionResult:
    auction_id: str
    task: TaskSpec
    status: str              # "bidding" | "accepted" | "executing" | "completed" | "failed"
    bids: list[Bid] = field(default_factory=list)
    winning_bid: Bid | None = None
    payment_method: str | None = None
    stripe_checkout_url: str | None = None
    execution_result: dict | None = None
    delivery_ipfs_cid: str | None = None
