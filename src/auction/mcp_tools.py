from dataclasses import asdict

from fastmcp import FastMCP

from auction.engine import AuctionEngine
from auction.models import TaskSpec


def register_auction_tools(mcp: FastMCP, engine: AuctionEngine) -> None:
    """Register fleet-level auction tools on the fleet MCP server (/fleet/mcp).

    These tools are for LLM clients connected to the fleet gateway. The
    external marketplace calls the per-robot tools (robot_submit_bid etc.)
    directly instead.
    """

    @mcp.tool
    async def fleet_request_bids(
        task_description: str,
        task_category: str,
        budget_ceiling: float,
        sla_seconds: int,
        capability_requirements: dict,
        requester_id: str = "fleet",
    ) -> dict:
        """Post a task to all capable robots and collect bids in parallel.

        task_category: "env_sensing" or "visual_inspection"
        budget_ceiling: maximum price in USD the buyer will pay (bids above
            this are excluded automatically)
        sla_seconds: time limit in seconds within which the task must complete
        capability_requirements: freeform dict, e.g. {"sensors_required": ["temperature"]}

        Returns the auction_id and the list of bids received. Pass auction_id
        to fleet_accept_bid to select a winner.
        """
        task = TaskSpec(
            task_description=task_description,
            task_category=task_category,
            budget_ceiling=budget_ceiling,
            sla_seconds=sla_seconds,
            capability_requirements=capability_requirements,
            requester_id=requester_id,
        )
        auction = await engine.request_bids(task)
        return asdict(auction)

    @mcp.tool
    async def fleet_list_auctions() -> dict:
        """List all active and recent auctions with a summary of their status.

        Returns a lightweight summary for each auction. Use fleet_get_auction_status
        with a specific auction_id for full details including execution results.
        """
        return {
            "auctions": [
                {
                    "auction_id": a.auction_id,
                    "status": a.status,
                    "task_category": a.task.task_category,
                    "task_description": a.task.task_description,
                    "bid_count": len(a.bids),
                    "winning_robot": a.winning_bid.robot_name if a.winning_bid else None,
                }
                for a in engine.auctions.values()
            ]
        }

    @mcp.tool
    async def fleet_accept_bid(auction_id: str, robot_name: str) -> dict:
        """Accept a specific robot's bid and advance the auction to 'accepted'.

        auction_id: returned by fleet_request_bids
        robot_name: the robot_name value from the bid you want to accept

        After accepting, call fleet_execute_task to run the task on the
        winning robot (or wait for the operator to approve if requires_approval
        is set in the robot's BiddingTerms).
        """
        auction = await engine.accept_bid(auction_id, robot_name)
        return asdict(auction)

    @mcp.tool
    async def fleet_execute_task(auction_id: str) -> dict:
        """Execute the accepted task on the winning robot.

        The auction must be in 'accepted' status (USDC / no-payment path) or
        'paid' status (Stripe payment confirmed). The robot is marked busy for
        the duration and the result is stored in the auction record.

        For Mode A (requires_approval=True, the default): call this tool after
        confirming payment to approve and trigger execution.
        For Mode B (requires_approval=False): execution is triggered automatically
        after Stripe payment confirmation — calling this tool is not required.

        Returns the delivery_data dict from the robot.
        """
        return await engine.execute(auction_id)

    @mcp.tool
    async def fleet_get_auction_status(auction_id: str) -> dict:
        """Get the full current state of an auction, including all bids and
        any execution result or delivery data."""
        return asdict(engine._get_auction(auction_id))
