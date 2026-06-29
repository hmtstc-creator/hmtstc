from __future__ import annotations

from copy import deepcopy

from services.real_trade_state_service import ensure_real_trade_state, is_unlock_valid, open_real_positions
from services.real_trade_service import build_real_readiness, build_order_safety_report
from services.binance_service import BinanceService, load_binance_runtime_config, map_binance_error


REAL_SAFETY_BLOCKER_GROUPS = {
    "environment": ["env_real_trading_disabled", "dry_run_active", "binance_credentials_missing"],
    "unlock": ["owner_unlock_missing_or_expired", "confirmation_token_not_found", "confirmation_token_payload_hash_mismatch", "confirmation_token_used", "confirmation_token_expired"],
    "runtime": ["runtime_health_degraded", "emergency_lock_active", "balance_reconciliation_lock_active", "manual_attention_required"],
    "limits": ["max_order_usdt_exceeded", "max_open_positions_reached", "max_open_real_positions_reached"],
    "symbol_filters": ["symbol_not_usdt_spot", "symbol_not_allowed_for_real", "symbol_blocked_for_real", "min_notional_not_met", "lot_size_step_size_mismatch", "market_lot_size_step_size_mismatch", "price_filter_tick_size_mismatch"],
    "balance": ["balance_not_readable", "insufficient_usdt_balance"],
}


def classify_blockers(blockers: list[str]) -> dict:
    groups = {key: [] for key in REAL_SAFETY_BLOCKER_GROUPS}
    groups["other"] = []
    for blocker in blockers or []:
        placed = False
        for group, known in REAL_SAFETY_BLOCKER_GROUPS.items():
            if blocker in known or any(str(blocker).startswith(k) for k in known):
                groups[group].append(blocker)
                placed = True
                break
        if not placed:
            groups["other"].append(blocker)
    return {k: sorted(set(v)) for k, v in groups.items() if v}


def build_real_order_safety_final_report(data: dict | None = None, settings: dict | None = None, order: dict | None = None, user: str = "system", role: str = "owner") -> dict:
    working_data = deepcopy(data or {})
    working_settings = deepcopy(settings or {})
    state = ensure_real_trade_state(working_data)
    runtime = load_binance_runtime_config()
    sample_order = order or {"symbol": "BTCUSDT", "side": "BUY", "quote_order_qty": min(5, runtime.max_order_usdt or 5)}
    readiness = build_real_readiness(working_data, working_settings)
    safety = build_order_safety_report(working_data, working_settings, sample_order, user=user, role=role)
    blockers = sorted(set((readiness.get("blockers") or []) + (safety.get("blockers") or [])))
    return {
        "status": "blocked" if blockers else "ready_for_confirmation",
        "real_order_allowed": False if runtime.real_trading_dry_run else not blockers,
        "dry_run": runtime.real_trading_dry_run,
        "owner_unlock_valid": is_unlock_valid(state),
        "open_real_positions": len(open_real_positions(state)),
        "blockers": blockers,
        "blocker_matrix": classify_blockers(blockers),
        "readiness": readiness,
        "sample_order_safety": safety,
        "contracts": {
            "preview_required_before_place": True,
            "confirmation_token_single_use": True,
            "confirmation_token_payload_hash_required": True,
            "dry_run_blocks_real_place": True,
            "order_payload_snapshot_required": True,
            "immutable_audit_required": True,
            "binance_spot_only": True,
            "withdraw_or_futures_authority": False,
        },
        "binance_error_mapping_samples": [
            map_binance_error({"code": -1021, "msg": "Timestamp for this request is outside recvWindow"}),
            map_binance_error({"code": -1013, "msg": "Filter failure: MIN_NOTIONAL"}),
            map_binance_error({"code": -2010, "msg": "Account has insufficient balance for requested action."}),
        ],
        "validator_contract": {
            "required_filters": ["MIN_NOTIONAL", "LOT_SIZE", "MARKET_LOT_SIZE", "PRICE_FILTER"],
            "validator": BinanceService.validate_market_order_payload.__name__,
        },
    }
