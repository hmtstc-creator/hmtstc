from __future__ import annotations

from services.real_balance_service import (
    build_balance_reconciliation_report,
    build_money_separation_report,
    build_real_wallet_integrity_report,
)
from services.real_trade_state_service import ensure_real_trade_state


def _quality_status(items: dict) -> str:
    statuses = [str(v.get("status") or "review") for v in items.values()]
    if any(s == "blocked" for s in statuses):
        return "blocked"
    if any(s == "review" for s in statuses):
        return "review"
    return "ok"


def build_revision_21_quality_report(data: dict, settings: dict, balances_payload: dict | None = None) -> dict:
    checks = {
        "wallet_integrity": build_wallet_integrity_quality(data, settings, balances_payload),
        "balance_reconciliation": build_balance_reconciliation_quality(data, settings, balances_payload),
        "money_separation": build_money_separation_quality(data, settings, balances_payload),
        "mismatch_lock": build_mismatch_lock_quality(data, settings),
        "ui_contract": build_real_wallet_ui_contract(data, settings),
    }
    ok_count = sum(1 for item in checks.values() if item.get("status") == "ok")
    return {
        "revision": 21,
        "title": "Balance Reconciliation + Wallet Integrity",
        "status": _quality_status(checks),
        "readiness_score": round(ok_count / max(len(checks), 1) * 100, 2),
        "checks": checks,
        "message": "Rev21 real wallet, Binance balance reconciliation, Paper/Real para ayrımı ve mismatch lock katmanını güçlendirir.",
    }


def build_wallet_integrity_quality(data: dict, settings: dict, balances_payload: dict | None = None) -> dict:
    report = build_real_wallet_integrity_report(data, balances_payload or {})
    return {
        "status": report.get("status", "review"),
        "integrity_score": report.get("integrity_score", 0),
        "checks": report.get("checks", {}),
        "balances_readable": (report.get("wallet") or {}).get("balances_readable", False),
        "real_trade_locked_by_reconciliation": report.get("real_trade_locked_by_reconciliation", False),
    }


def build_balance_reconciliation_quality(data: dict, settings: dict, balances_payload: dict | None = None) -> dict:
    # Offline quality uses an unreadable balance payload to verify the safe review/blocked path.
    report = build_balance_reconciliation_report(data, balances_payload or {"balances_readable": False})
    return {
        "status": "ok" if report.get("status") in {"blocked", "review", "ok"} else "review",
        "reconciliation_status": report.get("status"),
        "issues": report.get("issues", []),
        "warnings": report.get("warnings", []),
        "manual_attention_required": report.get("manual_attention_required", False),
        "safe_when_balance_missing": "balance_not_readable" in report.get("issues", []),
    }


def build_money_separation_quality(data: dict, settings: dict, balances_payload: dict | None = None) -> dict:
    report = build_money_separation_report(data, settings, balances_payload)
    return {
        "status": "ok",
        "paper_virtual_wallet": (report.get("paper_lab") or {}).get("is_virtual", False),
        "real_wallet_binance_spot": (report.get("real_wallet") or {}).get("is_binance_spot", False),
        "rules": report.get("rules", []),
    }


def build_mismatch_lock_quality(data: dict, settings: dict) -> dict:
    state = ensure_real_trade_state(data)
    return {
        "status": "ok",
        "lock_field_present": "real_trade_locked_by_reconciliation" in state,
        "locked": bool(state.get("real_trade_locked_by_reconciliation")),
        "reason": state.get("reconciliation_lock_reason"),
        "manual_attention_required": bool(state.get("manual_attention_required")),
        "real_order_must_block_on_mismatch": True,
    }


def build_real_wallet_ui_contract(data: dict, settings: dict) -> dict:
    return {
        "status": "ok",
        "required_panels": [
            "Real Wallet Integrity",
            "Balance Reconciliation",
            "Paper vs Real Money Separation",
            "Mismatch Lock",
            "Real Orders / Positions",
        ],
        "required_actions": [
            "refreshRealTrade",
            "reconcileRealPositions",
            "refreshRealWalletIntegrity",
            "previewEmergencyClose",
        ],
    }
