"""Unit tests for the Berlin Tumbller plugin.

Covers: pricing formula, rate limiter, availability map, audit log, and the
plugin's bid() branching. execute() with real HTTP is not exercised here —
that belongs in an integration test once the Cloudflare Tunnel is live.
"""

import json
from pathlib import Path

import pytest

from robots.berlin_tumbller import BerlinTumbllerPlugin
from robots.berlin_tumbller import audit, availability, pricing, rate_limit


# ── pricing ────────────────────────────────────────────────────────────


class TestPricing:
    def test_single_command_is_floor(self):
        assert pricing.compute_price_cents(1) == 50
        assert pricing.compute_price_cents(0) == 50  # edge: no commands, still floor

    def test_extra_commands_add_one_cent_each(self):
        assert pricing.compute_price_cents(2) == 51
        assert pricing.compute_price_cents(10) == 59

    def test_usd_wrapper_matches_cents(self):
        assert pricing.compute_price_usd(1) == 0.50
        assert pricing.compute_price_usd(10) == 0.59


# ── rate limiter ───────────────────────────────────────────────────────


class TestRateLimiter:
    def test_allows_up_to_cap(self):
        rl = rate_limit.SlidingWindowRateLimiter(max_requests=3, window_seconds=60)
        assert rl.allow(now=0) is True
        assert rl.allow(now=0) is True
        assert rl.allow(now=0) is True
        assert rl.allow(now=0) is False  # 4th request in same window

    def test_window_slides(self):
        rl = rate_limit.SlidingWindowRateLimiter(max_requests=2, window_seconds=10)
        assert rl.allow(now=0) is True
        assert rl.allow(now=5) is True
        assert rl.allow(now=9) is False       # still within window
        assert rl.allow(now=11) is True       # first timestamp now evicted

    def test_remaining_reflects_usage(self):
        rl = rate_limit.SlidingWindowRateLimiter(max_requests=5, window_seconds=60)
        assert rl.remaining(now=0) == 5
        rl.allow(now=0)
        rl.allow(now=0)
        assert rl.remaining(now=0) == 3


# ── availability map ───────────────────────────────────────────────────


class TestAvailability:
    def test_capability_available(self):
        m = {"movement": {"available": True}}
        ok, reason = availability.is_available("movement", m)
        assert ok is True
        assert reason is None

    def test_capability_marked_unavailable(self):
        m = {"temperature": {"available": False, "reason": "SHT30 not wired"}}
        ok, reason = availability.is_available("temperature", m)
        assert ok is False
        assert reason == "SHT30 not wired"

    def test_missing_capability_treated_as_unavailable(self):
        ok, reason = availability.is_available("visual", {})
        assert ok is False
        assert reason is not None and "not declared" in reason

    def test_task_category_to_capability(self):
        assert availability.capability_for_task_category("delivery_ground") == "movement"
        assert availability.capability_for_task_category("env_sensing") == "temperature"
        assert availability.capability_for_task_category("unknown_category") is None

    def test_load_handles_missing_file(self, monkeypatch):
        monkeypatch.setenv("BERLIN_TUMBLLER_AVAILABILITY_PATH", "/nonexistent/path.json")
        assert availability.load() == {}


# ── audit log ──────────────────────────────────────────────────────────


class TestAudit:
    def test_appends_jsonl(self, tmp_path: Path):
        target = tmp_path / "audit.jsonl"
        audit.append({"task_id": "t1", "completion": "completed"}, path=target)
        audit.append({"task_id": "t2", "completion": "aborted"}, path=target)

        lines = target.read_text().strip().split("\n")
        assert len(lines) == 2
        rows = [json.loads(line) for line in lines]
        assert rows[0]["task_id"] == "t1"
        assert rows[1]["task_id"] == "t2"
        assert "ts" in rows[0]  # auto-stamped

    def test_creates_parent_dirs(self, tmp_path: Path):
        target = tmp_path / "nested/deep/audit.jsonl"
        audit.append({"x": 1}, path=target)
        assert target.exists()


# ── plugin.bid() ──────────────────────────────────────────────────────


@pytest.fixture
def plugin(monkeypatch, tmp_path: Path):
    # Point availability at a writable file in tmp so tests don't depend on the default
    avail_file = tmp_path / "availability.json"
    avail_file.write_text(
        json.dumps(
            {
                "movement": {"available": True},
                "temperature": {"available": False, "reason": "SHT30 not wired"},
            }
        )
    )
    monkeypatch.setenv("BERLIN_TUMBLLER_AVAILABILITY_PATH", str(avail_file))
    return BerlinTumbllerPlugin()


class TestBid:
    @pytest.mark.asyncio
    async def test_accepts_delivery_ground_when_available(self, plugin):
        result = await plugin.bid(
            {
                "task_category": "delivery_ground",
                "budget_ceiling": 1.00,
                "capability_requirements": {"move_count": 3},
            }
        )
        assert result is not None
        assert result["currency"] == "usdc"
        assert result["price"] == 0.52  # 50 + 2*1 cents
        assert "movement" in result["capabilities_offered"]

    @pytest.mark.asyncio
    async def test_declines_non_delivery_ground(self, plugin):
        result = await plugin.bid(
            {"task_category": "aerial_survey", "budget_ceiling": 10.00, "capability_requirements": {}}
        )
        assert result is None

    @pytest.mark.asyncio
    async def test_declines_when_movement_offline(self, plugin, monkeypatch, tmp_path):
        avail_file = tmp_path / "offline.json"
        avail_file.write_text(json.dumps({"movement": {"available": False, "reason": "under maintenance"}}))
        monkeypatch.setenv("BERLIN_TUMBLLER_AVAILABILITY_PATH", str(avail_file))
        result = await plugin.bid(
            {"task_category": "delivery_ground", "budget_ceiling": 1.00, "capability_requirements": {}}
        )
        assert result is None

    @pytest.mark.asyncio
    async def test_declines_when_budget_below_floor(self, plugin):
        result = await plugin.bid(
            {"task_category": "delivery_ground", "budget_ceiling": 0.10, "capability_requirements": {}}
        )
        assert result is None

    @pytest.mark.asyncio
    async def test_declines_when_buyer_requires_unsupported_sensor(self, plugin):
        result = await plugin.bid(
            {
                "task_category": "delivery_ground",
                "budget_ceiling": 1.00,
                "capability_requirements": {"sensors_required": ["thermal_camera"]},
            }
        )
        assert result is None
