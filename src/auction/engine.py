import asyncio
import logging
import uuid
from dataclasses import asdict

from core.plugin import RobotPlugin
from auction.models import AuctionResult, Bid, TaskSpec

logger = logging.getLogger(__name__)


class AuctionEngine:
    def __init__(self, plugins: dict[str, RobotPlugin]):
        self.plugins = plugins
        self.auctions: dict[str, AuctionResult] = {}
        self._busy: set[str] = set()  # robot names currently executing a task

    async def request_bids(self, task: TaskSpec) -> AuctionResult:
        """Fan out bid requests to all plugins in parallel and collect responses.

        Plugins that are busy, decline, raise, or bid above the budget ceiling
        are excluded from the result. Budget-ceiling filtering is a safety net —
        plugins are expected to check budget_ceiling themselves in bid().
        """
        task_dict = asdict(task)

        async def _bid_one(name: str, plugin: RobotPlugin) -> Bid | None:
            if name in self._busy:
                return None
            try:
                result = await plugin.bid(task_dict)
                if result is None:
                    return None
                price = float(result.get("price", 0))
                if price > task.budget_ceiling:
                    return None
                return Bid(
                    robot_name=name,
                    willing_to_bid=True,
                    price=price,
                    currency=result.get("currency", "usd"),
                    sla_commitment_seconds=int(result.get("sla_commitment_seconds", 0)),
                    # fakerover uses "ai_confidence"; plan target field is "confidence"
                    confidence=float(result.get("confidence", result.get("ai_confidence", 0.5))),
                    capabilities_offered=result.get("capabilities_offered", []),
                    notes=result.get("notes", ""),
                    reason="",
                )
            except Exception as exc:
                logger.warning("Plugin %r bid() failed: %s", name, exc)
                return None

        results = await asyncio.gather(
            *(_bid_one(name, plugin) for name, plugin in self.plugins.items()),
        )
        bids = [b for b in results if b is not None]

        auction_id = str(uuid.uuid4())
        auction = AuctionResult(
            auction_id=auction_id,
            task=task,
            status="bidding",
            bids=bids,
        )
        self.auctions[auction_id] = auction
        return auction

    async def accept_bid(self, auction_id: str, robot_name: str) -> AuctionResult:
        """Mark the named robot's bid as the winner. Status moves to 'accepted'."""
        auction = self._get_auction(auction_id)
        if auction.status != "bidding":
            raise ValueError(
                f"Auction {auction_id} cannot be accepted (status: {auction.status!r})"
            )
        winning = next((b for b in auction.bids if b.robot_name == robot_name), None)
        if winning is None:
            raise ValueError(f"No bid from robot {robot_name!r} in auction {auction_id}")
        auction.winning_bid = winning
        auction.status = "accepted"
        return auction

    async def execute(self, auction_id: str) -> dict:
        """Execute the accepted task on the winning robot.

        Marks the robot as busy for the duration, updates auction status, and
        returns the result dict from plugin.execute(). On any error the auction
        is marked 'failed' and the exception message is captured in
        execution_result.
        """
        auction = self._get_auction(auction_id)
        if auction.status != "accepted":
            raise ValueError(
                f"Auction {auction_id} must be 'accepted' before executing (status: {auction.status!r})"
            )

        if auction.winning_bid is None:
            raise ValueError(
                f"Auction {auction_id} has status 'accepted' but no winning_bid is set"
            )

        robot_name = auction.winning_bid.robot_name
        plugin = self.plugins.get(robot_name)
        if plugin is None:
            raise ValueError(f"Plugin {robot_name!r} not found in registered plugins")

        if robot_name in self._busy:
            raise RuntimeError(f"Robot {robot_name!r} is already executing a task")

        self._busy.add(robot_name)
        auction.status = "executing"
        try:
            result = await plugin.execute(
                auction_id,
                auction.task.task_description,
                auction.task.capability_requirements,
            )
            auction.execution_result = result
            auction.status = "completed" if result.get("success", False) else "failed"
        except Exception as exc:
            auction.status = "failed"
            result = {"success": False, "error": str(exc)}
            auction.execution_result = result
        finally:
            self._busy.discard(robot_name)

        return result

    def _get_auction(self, auction_id: str) -> AuctionResult:
        auction = self.auctions.get(auction_id)
        if auction is None:
            raise KeyError(f"Auction {auction_id!r} not found")
        return auction
