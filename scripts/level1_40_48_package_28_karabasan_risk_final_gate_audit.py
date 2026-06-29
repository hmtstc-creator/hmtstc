#!/usr/bin/env python3
from __future__ import annotations

import sys
from copy import deepcopy
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from services.karabasan_final_decision_service import build_karabasan_final_decision, karabasan_decision_view  # noqa: E402
from services.karabasan_hard_block_service import build_karabasan_hard_blocks  # noqa: E402


def main() -> int:
    settings = {
        "coin_filter": {"min_quote_volume": 1_000_000},
        "risk": {"max_spread_percent": 0.35, "daily_loss_limit": "30 USDT"},
        "bot": {"max_open_positions": 5, "usdt_per_position": 10, "allocated_usdt": 100},
        "karabasan": {"minimum_score": 60, "target_profit_pct": 2, "stop_loss_pct": 0.5, "binance_roundtrip_fee_pct": 0, "system_roundtrip_commission_pct": 0},
    }
    runtime = {"bot_running": True, "engine_status": "running", "last_scan": {"status": "ok", "live": True}, "open_positions": [], "history": []}
    strategy = {
        "symbol": "TESTUSDT", "passed": True, "price": 10, "quote_volume": 10_000_000,
        "spread_percent": 0.05, "quality_score": 90, "target_profit_pct": 2, "stop_loss_pct": 0.5,
        "strategy_output": {"strategy_id": "S1", "symbol": "TESTUSDT", "signal": "BUY", "confidence": 90, "entry_reason": "ok", "invalid_reasons": []},
    }
    approved = build_karabasan_final_decision(runtime, settings, strategy)
    api_down = build_karabasan_hard_blocks({**runtime, "last_scan": {}}, settings, strategy)
    bot_off = build_karabasan_hard_blocks({**runtime, "bot_running": False}, settings, strategy)
    spread = build_karabasan_hard_blocks(runtime, settings, {**strategy, "spread_percent": 1.0})
    liquidity = build_karabasan_hard_blocks(runtime, settings, {**strategy, "quote_volume": 10})
    same_coin_runtime = deepcopy(runtime)
    same_coin_runtime["open_positions"] = [{"symbol": "TESTUSDT", "side": "LONG", "usdt_size": 10}]
    same_coin = build_karabasan_hard_blocks(same_coin_runtime, settings, strategy)
    loss_runtime = {**runtime, "history": [{"pnl": -50, "closed_at": "2026-06-15T10:00:00"}]}
    loss = build_karabasan_hard_blocks(loss_runtime, settings, strategy)

    bot_text = (ROOT / "backend" / "services" / "bot_service.py").read_text(encoding="utf-8")
    routes = (ROOT / "backend" / "routes" / "karabasan_routes.py").read_text(encoding="utf-8")
    checks = {
        "final_schema_complete": set(approved).issuperset({"approved", "score", "blocks", "warnings"}),
        "valid_strategy_can_be_approved": approved["approved"] is True and not approved["blocks"],
        "api_hard_block": "api_unavailable" in api_down["blocks"],
        "bot_hard_block": "bot_not_running" in bot_off["blocks"],
        "spread_hard_block": "spread_limit_exceeded" in spread["blocks"],
        "liquidity_hard_block": "liquidity_below_minimum" in liquidity["blocks"],
        "same_coin_hard_block": "symbol_already_open" in same_coin["blocks"],
        "daily_loss_hard_block": "daily_loss_limit_reached" in loss["blocks"],
        "user_view_hides_owner_details": "owner_details" not in karabasan_decision_view(approved, owner=False) and "owner_details" in karabasan_decision_view(approved, owner=True),
        "bot_gates_before_position": bot_text.index("build_karabasan_final_decision") < bot_text.index("create_shadow_position("),
        "post_final_decision_endpoint": '@router.post("/final-decision")' in routes,
    }
    failed = [name for name, passed in checks.items() if not passed]
    if failed:
        print("LEVEL1_40_48_PACKAGE_28_KARABASAN_RISK_FINAL_GATE_AUDIT_FAIL")
        print("failed=" + ",".join(failed))
        return 1
    print("LEVEL1_40_48_PACKAGE_28_KARABASAN_RISK_FINAL_GATE_AUDIT_OK")
    print("status=ok")
    print(f"checks={len(checks)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
