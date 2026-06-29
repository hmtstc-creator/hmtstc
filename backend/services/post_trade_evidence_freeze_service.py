from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

REVISION_RANGE = "1011-1015"
PACKAGE_NAME = "Post-Trade Evidence & Freeze Block"
FINAL_DECISION_READY = "POST_TRADE_EVIDENCE_FREEZE_READY"
DRILL_USERNAME = "rev1011_post_trade_evidence_freeze"

DEFAULT_MAX_FEE_BPS = 12.0
DEFAULT_MAX_SLIPPAGE_BPS = 10.0
DEFAULT_MAX_LATENCY_MS = 1500
FORBIDDEN_TOKENS = (
    "api_key",
    "api_secret",
    "secret_key",
    "binance_secret",
    "private_key",
    "activation_token",
    "raw_token",
)


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _as_dict(value: Any) -> dict:
    return value if isinstance(value, dict) else {}


def _as_list(value: Any) -> list:
    return value if isinstance(value, list) else []


def _safe_float(value: Any, fallback: float = 0.0) -> float:
    try:
        if value is None or value == "":
            return fallback
        return float(value)
    except (TypeError, ValueError):
        return fallback


def _safe_int(value: Any, fallback: int = 0) -> int:
    try:
        if value is None or value == "":
            return fallback
        return int(float(value))
    except (TypeError, ValueError):
        return fallback


def _status_text(value: Any) -> str:
    return str(value or "").strip().upper()


def _safe_sample(username: str = DRILL_USERNAME) -> dict[str, Any]:
    return {
        "username": username,
        "session_id": "REV1011-1015-OFFLINE-EVIDENCE",
        "symbol": "BTCUSDT",
        "orders": [
            {
                "client_order_id": "REV1011-SAFE-PREVIEW-ORDER",
                "exchange_order_id": "offline-order-1011",
                "status": "FILLED",
                "side": "BUY",
                "type": "MARKET",
                "requested_qty": 0.001,
                "executed_qty": 0.001,
                "requested_price": 50000.0,
                "average_fill_price": 50001.0,
            }
        ],
        "fills": [
            {
                "fill_id": "offline-fill-1012",
                "qty": 0.001,
                "price": 50001.0,
                "fee_usdt": 0.05,
                "latency_ms": 240,
                "slippage_bps": 2.0,
            }
        ],
        "position": {
            "symbol": "BTCUSDT",
            "qty": 0.001,
            "entry_price": 50001.0,
            "exit_price": 50011.0,
            "realized_pnl_usdt": 0.01,
        },
        "journal": [
            {
                "event": "ENTRY_FILLED",
                "client_order_id": "REV1011-SAFE-PREVIEW-ORDER",
                "qty": 0.001,
                "price": 50001.0,
            },
            {
                "event": "PNL_RECORDED",
                "realized_pnl_usdt": 0.01,
                "fee_usdt": 0.05,
            },
        ],
        "pnl": {"realized_pnl_usdt": 0.01, "journal_pnl_usdt": 0.01},
        "fees": {"total_fee_usdt": 0.05, "fee_bps": 10.0},
        "latency": {"observed_ms": 240},
        "slippage": {"observed_bps": 2.0},
    }


def _evidence(payload: dict | None, username: str = DRILL_USERNAME) -> dict[str, Any]:
    evidence = _safe_sample(username)
    supplied = _as_dict(payload)
    for key in ("session_id", "symbol", "orders", "fills", "position", "journal", "pnl", "fees", "latency", "slippage"):
        if key in supplied:
            evidence[key] = supplied[key]
    return evidence


def _command_preview() -> dict[str, Any]:
    return {
        "places_order": False,
        "submits_close_order": False,
        "emergency_close_triggered": False,
        "sends_exchange_request": False,
        "binance_network_call_triggered": False,
        "reads_secret_store": False,
        "logs_secret_values": False,
        "network_default_off": True,
        "real_submit_default_off": True,
        "real_close_default_off": True,
        "emergency_close_default_off": True,
        "auto_repeat": False,
        "auto_scale": False,
        "auto_apply": False,
        "report_only": True,
    }


def _check(name: str, status: str, detail: str) -> dict[str, Any]:
    return {"name": name, "status": status, "detail": detail}


def _totals(checks: list[dict]) -> dict[str, int]:
    return {
        "total": len(checks),
        "ok": sum(1 for check in checks if check.get("status") == "ok"),
        "review": sum(1 for check in checks if check.get("status") == "review"),
        "blocked": sum(1 for check in checks if check.get("status") == "blocked"),
    }


def _status_from_checks(checks: list[dict]) -> str:
    statuses = {str(check.get("status")) for check in checks}
    if "blocked" in statuses:
        return "blocked"
    if "review" in statuses:
        return "review"
    return "ok"


def _blockers(checks: list[dict]) -> list[str]:
    return [str(check.get("name")) for check in checks if check.get("status") == "blocked"]


def _leak_scan(payload: dict[str, Any]) -> dict[str, Any]:
    serialized = json.dumps(payload, ensure_ascii=False).lower()
    found = [token for token in FORBIDDEN_TOKENS if token in serialized]
    return {"status": "PASS" if not found else "FAIL", "forbidden_tokens_found": found}


def build_rev1011_exchange_order_status_collector(payload: dict | None = None, username: str = DRILL_USERNAME) -> dict[str, Any]:
    evidence = _evidence(payload, username)
    orders = _as_list(evidence.get("orders"))
    statuses = [_status_text(order.get("status")) for order in orders if isinstance(order, dict)]
    terminal = {"FILLED", "PARTIALLY_FILLED", "REJECTED", "CANCELED", "EXPIRED"}
    checks = [
        _check("order_evidence_present", "ok" if orders else "blocked", "Exchange order status evidence must be attached offline."),
        _check("terminal_status_present", "ok" if any(status in terminal for status in statuses) else "blocked", "At least one terminal or partial terminal status is required."),
        _check("network_default_off", "ok", "Collector is report-only and does not call Binance."),
    ]
    body = {
        "session_id": evidence.get("session_id"),
        "symbol": evidence.get("symbol"),
        "order_count": len(orders),
        "statuses": statuses,
        "filled_count": statuses.count("FILLED"),
        "partial_count": statuses.count("PARTIALLY_FILLED"),
        "rejected_count": statuses.count("REJECTED"),
        "canceled_count": statuses.count("CANCELED"),
        "collector_mode": "OFFLINE_EVIDENCE_ONLY",
        "binance_network_call_triggered": False,
    }
    return {
        "revision": 1011,
        "name": "exchange_order_status_collector",
        "status": _status_from_checks(checks),
        "blockers": _blockers(checks),
        "order_status_collector": body,
        "checks": checks,
        "check_totals": _totals(checks),
        "command_preview": _command_preview(),
        "secret_values_returned": False,
    }


def build_rev1012_fill_partial_rejected_analysis(payload: dict | None = None, username: str = DRILL_USERNAME) -> dict[str, Any]:
    evidence = _evidence(payload, username)
    rev1011 = build_rev1011_exchange_order_status_collector(evidence, username)
    fills = _as_list(evidence.get("fills"))
    statuses = _as_list(_as_dict(rev1011.get("order_status_collector")).get("statuses"))
    requested_qty = sum(_safe_float(order.get("requested_qty"), 0.0) for order in _as_list(evidence.get("orders")) if isinstance(order, dict))
    executed_qty = sum(_safe_float(order.get("executed_qty"), 0.0) for order in _as_list(evidence.get("orders")) if isinstance(order, dict))
    fill_ratio = round(executed_qty / requested_qty, 6) if requested_qty else 0.0
    rejected = "REJECTED" in statuses
    partial = "PARTIALLY_FILLED" in statuses or (0 < fill_ratio < 1)
    checks = [
        _check("fill_evidence_present", "ok" if fills else "blocked", "Fill evidence is required for post-trade analysis."),
        _check("rejected_order_flagged", "blocked" if rejected else "ok", "Rejected orders freeze repeat until operator review."),
        _check("partial_fill_classified", "review" if partial else "ok", "Partial fills require quantity/PnL review before repeat."),
    ]
    body = {
        "fill_count": len(fills),
        "requested_qty": requested_qty,
        "executed_qty": executed_qty,
        "fill_ratio": fill_ratio,
        "classification": "REJECTED" if rejected else "PARTIAL_FILL" if partial else "FILLED",
        "repeat_requires_owner_review": True,
        "scale_allowed": False,
    }
    return {
        "revision": 1012,
        "name": "fill_partial_rejected_analysis",
        "status": _status_from_checks(checks),
        "blockers": _blockers(checks),
        "fill_analysis": body,
        "checks": checks,
        "check_totals": _totals(checks),
        "command_preview": _command_preview(),
        "secret_values_returned": False,
    }


def build_rev1013_position_journal_pnl_reconciliation(payload: dict | None = None, username: str = DRILL_USERNAME) -> dict[str, Any]:
    evidence = _evidence(payload, username)
    position = _as_dict(evidence.get("position"))
    journal = _as_list(evidence.get("journal"))
    pnl = _as_dict(evidence.get("pnl"))
    position_pnl = _safe_float(position.get("realized_pnl_usdt"), 0.0)
    reported_pnl = _safe_float(pnl.get("realized_pnl_usdt"), position_pnl)
    journal_pnl = _safe_float(pnl.get("journal_pnl_usdt"), reported_pnl)
    pnl_delta = round(abs(reported_pnl - journal_pnl), 8)
    checks = [
        _check("position_present", "ok" if position else "blocked", "Position snapshot must be present."),
        _check("journal_present", "ok" if journal else "blocked", "Journal evidence must be present."),
        _check("pnl_reconciled", "ok" if pnl_delta <= 0.00000001 else "blocked", "Position and journal PnL must reconcile."),
    ]
    body = {
        "position_symbol": position.get("symbol"),
        "position_qty": _safe_float(position.get("qty"), 0.0),
        "realized_pnl_usdt": reported_pnl,
        "journal_pnl_usdt": journal_pnl,
        "pnl_delta_usdt": pnl_delta,
        "journal_count": len(journal),
        "reconciliation": "CONSISTENT" if _status_from_checks(checks) == "ok" else "INCONSISTENT",
        "freeze_required": _status_from_checks(checks) != "ok",
    }
    return {
        "revision": 1013,
        "name": "position_journal_pnl_reconciliation",
        "status": _status_from_checks(checks),
        "blockers": _blockers(checks),
        "position_journal_pnl_reconciliation": body,
        "checks": checks,
        "check_totals": _totals(checks),
        "command_preview": _command_preview(),
        "secret_values_returned": False,
    }


def build_rev1014_fee_slippage_latency_reality_check(payload: dict | None = None, username: str = DRILL_USERNAME) -> dict[str, Any]:
    evidence = _evidence(payload, username)
    fees = _as_dict(evidence.get("fees"))
    slippage = _as_dict(evidence.get("slippage"))
    latency = _as_dict(evidence.get("latency"))
    fee_bps = _safe_float(fees.get("fee_bps"), 0.0)
    slippage_bps = _safe_float(slippage.get("observed_bps"), 0.0)
    latency_ms = _safe_int(latency.get("observed_ms"), 0)
    checks = [
        _check("fee_within_reality_limit", "ok" if fee_bps <= DEFAULT_MAX_FEE_BPS else "blocked", "Fee cost must stay within the post-trade limit."),
        _check("slippage_within_reality_limit", "ok" if slippage_bps <= DEFAULT_MAX_SLIPPAGE_BPS else "blocked", "Slippage must stay within the post-trade limit."),
        _check("latency_within_reality_limit", "ok" if latency_ms <= DEFAULT_MAX_LATENCY_MS else "review", "Latency over limit requires execution path review."),
    ]
    body = {
        "fee_bps": fee_bps,
        "max_fee_bps": DEFAULT_MAX_FEE_BPS,
        "slippage_bps": slippage_bps,
        "max_slippage_bps": DEFAULT_MAX_SLIPPAGE_BPS,
        "latency_ms": latency_ms,
        "max_latency_ms": DEFAULT_MAX_LATENCY_MS,
        "reality_check": "PASS" if _status_from_checks(checks) == "ok" else "ATTENTION",
        "cost_model_auto_apply": False,
    }
    return {
        "revision": 1014,
        "name": "fee_slippage_latency_reality_check",
        "status": _status_from_checks(checks),
        "blockers": _blockers(checks),
        "fee_slippage_latency_reality_check": body,
        "checks": checks,
        "check_totals": _totals(checks),
        "command_preview": _command_preview(),
        "secret_values_returned": False,
    }


def build_post_trade_evidence_freeze_report(payload: dict | None = None, username: str = DRILL_USERNAME) -> dict[str, Any]:
    evidence = _evidence(payload, username)
    rev1011 = build_rev1011_exchange_order_status_collector(evidence, username)
    rev1012 = build_rev1012_fill_partial_rejected_analysis(evidence, username)
    rev1013 = build_rev1013_position_journal_pnl_reconciliation(evidence, username)
    rev1014 = build_rev1014_fee_slippage_latency_reality_check(evidence, username)
    checks: list[dict] = []
    blockers: list[str] = []
    for key, part in (
        ("rev1011", rev1011),
        ("rev1012", rev1012),
        ("rev1013", rev1013),
        ("rev1014", rev1014),
    ):
        checks.extend(_as_list(part.get("checks")))
        blockers.extend([f"{key}:{blocker}" for blocker in _as_list(part.get("blockers"))])
    safety_scope = {
        "real_order_submit_triggered": False,
        "real_order_close_triggered": False,
        "emergency_close_triggered": False,
        "binance_network_call_triggered": False,
        "secret_store_read": False,
        "runtime_write_triggered": False,
        "network_default_off": True,
        "auto_repeat_allowed": False,
        "scale_allowed": False,
        "auto_apply": False,
    }
    freeze = {
        "decision": "POST_TRADE_FREEZE_FOR_OPERATOR_REVIEW",
        "repeat_requires_owner_review": True,
        "scale_allowed": False,
        "auto_repeat_allowed": False,
        "next_allowed_action": "review_post_trade_evidence_before_any_repeat",
    }
    report = {
        "status": "ok" if not blockers else "blocked",
        "revision": 1015,
        "revision_range": REVISION_RANGE,
        "package": PACKAGE_NAME,
        "generated_at": now_iso(),
        "username": evidence.get("username") or username,
        "final_decision": FINAL_DECISION_READY if not blockers else "BLOCKED",
        "blockers": blockers,
        "checks": {
            "rev1011_exchange_order_status_collector": rev1011,
            "rev1012_fill_partial_rejected_analysis": rev1012,
            "rev1013_position_journal_pnl_reconciliation": rev1013,
            "rev1014_fee_slippage_latency_reality_check": rev1014,
        },
        "check_totals": _totals(checks),
        "freeze_report": freeze,
        "safety_scope": safety_scope,
        "command_preview": _command_preview(),
        "secret_values_returned": False,
        "operator_next_steps": [
            "Keep real submit, close and emergency close disabled.",
            "Review order status, fill classification, position/journal/PnL reconciliation, fee/slippage and latency evidence together.",
            "Do not repeat or scale until owner review accepts the post-trade evidence freeze report.",
        ],
    }
    report["leak_scan"] = _leak_scan(report)
    if report["leak_scan"]["status"] != "PASS":
        report["status"] = "blocked"
        report["final_decision"] = "BLOCKED"
        report["blockers"].append("forbidden_secret_token_leak_detected")
    return report


def build_post_trade_evidence_freeze_summary(payload: dict | None = None, username: str = DRILL_USERNAME) -> dict[str, Any]:
    report = build_post_trade_evidence_freeze_report(payload, username)
    freeze = _as_dict(report.get("freeze_report"))
    safety = _as_dict(report.get("safety_scope"))
    return {
        "status": report["status"],
        "revision": report["revision"],
        "revision_range": report["revision_range"],
        "final_decision": report["final_decision"],
        "blocker_count": len(report["blockers"]),
        "freeze_decision": freeze.get("decision"),
        "repeat_requires_owner_review": freeze.get("repeat_requires_owner_review"),
        "scale_allowed": freeze.get("scale_allowed"),
        "auto_repeat_allowed": freeze.get("auto_repeat_allowed"),
        "real_order_submit_triggered": safety.get("real_order_submit_triggered"),
        "real_order_close_triggered": safety.get("real_order_close_triggered"),
        "emergency_close_triggered": safety.get("emergency_close_triggered"),
        "binance_network_call_triggered": safety.get("binance_network_call_triggered"),
        "secret_values_returned": False,
    }
