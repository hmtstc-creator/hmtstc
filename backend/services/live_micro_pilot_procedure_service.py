from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import uuid4

from core.storage import append_audit, now_iso
from services.real_pilot_service import build_pilot_report, pilot_config, pilot_readiness
from services.real_trade_service import build_real_readiness, read_real_balances, reconcile_real_positions
from services.real_trade_state_service import ensure_real_trade_state, lock_real_trading, open_real_positions

REV36_STEPS = [
    {
        "id": "readonly_precheck",
        "order": 1,
        "title": "Readonly readiness precheck",
        "endpoint": "GET /api/real/readiness",
        "required": True,
        "description": "Binance/API/readiness/pilot config okunur; emir üretilmez.",
    },
    {
        "id": "dry_run_rehearsal",
        "order": 2,
        "title": "Dry-run rehearsal",
        "endpoint": "POST /api/real/orders/dry-run",
        "required": True,
        "description": "Aynı sembol/tutarla dry-run denenir; gerçek emir yoktur.",
    },
    {
        "id": "confirmation_token_preview",
        "order": 3,
        "title": "Confirmation token preview",
        "endpoint": "POST /api/real/orders/preview",
        "required": True,
        "description": "Preview tek kullanımlık token üretir; payload ve tutar değişirse geçersizdir.",
    },
    {
        "id": "tiny_real_order_window",
        "order": 4,
        "title": "Tiny real order guarded window",
        "endpoint": "POST /api/real/orders/place",
        "required": True,
        "description": "Sadece owner unlock + token + pilot limitleri + readiness kapıları tamamsa tiny order denenebilir.",
    },
    {
        "id": "tracking",
        "order": 5,
        "title": "Tracking and lifecycle watch",
        "endpoint": "GET /api/real/positions/lifecycle",
        "required": True,
        "description": "Order/position state izlenir; manual_attention oluşursa pilot durur.",
    },
    {
        "id": "reconciliation",
        "order": 6,
        "title": "Balance reconciliation",
        "endpoint": "POST /api/real/positions/reconcile",
        "required": True,
        "description": "Bot state ile Binance bakiyesi karşılaştırılır; mismatch real lock üretir.",
    },
    {
        "id": "auto_lock",
        "order": 7,
        "title": "Pilot auto-lock",
        "endpoint": "POST /api/real/pilot/finalize",
        "required": True,
        "description": "Pilot bittiğinde real trading kilitlenir ve owner unlock sıfırlanır.",
    },
    {
        "id": "final_report",
        "order": 8,
        "title": "Final pilot report",
        "endpoint": "GET /api/real/pilot/report",
        "required": True,
        "description": "Pilot raporu audit, orders, positions, reconcile ve blocker özetiyle üretilir.",
    },
]


def _float(value: Any, default: float = 0.0) -> float:
    try:
        return float(str(value if value is not None else default).replace(",", "."))
    except Exception:
        return float(default)


def _safe_order_payload(order: dict | None, cfg: dict) -> dict:
    order = order or {}
    allowed = cfg.get("allowed_symbols") or ["BTCUSDT"]
    symbol = str(order.get("symbol") or allowed[0]).upper().strip()
    side = str(order.get("side") or "BUY").upper().strip()
    quote_order_qty = _float(order.get("quote_order_qty") or order.get("amount_usdt") or min(5, cfg.get("max_order_usdt") or 5), 5)
    return {
        "symbol": symbol,
        "side": side if side in {"BUY", "SELL"} else "BUY",
        "quote_order_qty": quote_order_qty,
    }


def _phase_status(phase_id: str, blockers: list[str], warnings: list[str], ok: bool) -> dict:
    return {
        "phase_id": phase_id,
        "status": "ready" if ok and not blockers else "blocked",
        "blockers": sorted(set(blockers)),
        "warnings": sorted(set(warnings)),
    }


def build_live_micro_pilot_runbook(data: dict, settings: dict) -> dict:
    state = ensure_real_trade_state(data)
    cfg = pilot_config()
    readiness = build_real_readiness(data, settings)
    pilot = pilot_readiness(data, settings)
    balances = read_real_balances()
    open_positions = open_real_positions(state)

    global_blockers: list[str] = []
    warnings: list[str] = []
    if not cfg.get("enabled"):
        global_blockers.append("pilot_env_disabled")
    if not readiness.get("ready_for_dry_run"):
        global_blockers.append("dry_run_readiness_missing")
    if state.get("emergency_lock") or data.get("emergency_lock"):
        global_blockers.append("emergency_lock_active")
    if state.get("manual_attention_required"):
        global_blockers.append("manual_attention_required")
    if state.get("real_trade_locked_by_reconciliation"):
        global_blockers.append("reconciliation_lock_active")
    if balances.get("status") != "ok":
        warnings.append("balance_read_not_ok")

    phases = [
        _phase_status("readonly_precheck", [], warnings, True),
        _phase_status("dry_run_rehearsal", [b for b in global_blockers if b != "pilot_env_disabled"], [], bool(readiness.get("ready_for_dry_run"))),
        _phase_status("confirmation_token_preview", list(global_blockers), [], not global_blockers),
        _phase_status("tiny_real_order_window", list(pilot.get("blockers") or []) + (["owner_unlock_missing"] if not state.get("owner_unlocked") else []), ["real_order_requires_token_and_owner_approval"], not pilot.get("blockers")),
        _phase_status("tracking", ["open_position_limit_reached"] if len(open_positions) > int(cfg.get("max_open_positions") or 1) else [], [], True),
        _phase_status("reconciliation", [], ["must_run_after_any_real_attempt"], True),
        _phase_status("auto_lock", [], ["always_lock_after_finish"], True),
        _phase_status("final_report", [], [], True),
    ]
    blocked_phases = [p for p in phases if p["status"] == "blocked"]
    return {
        "status": "blocked" if blocked_phases else "ready",
        "revision": 36,
        "title": "Live Micro Pilot Procedure",
        "procedure": REV36_STEPS,
        "phases": phases,
        "global_blockers": sorted(set(global_blockers)),
        "warnings": sorted(set(warnings)),
        "pilot_config": cfg,
        "pilot_readiness": pilot,
        "real_readiness": readiness,
        "open_real_positions": len(open_positions),
        "hard_rules": [
            "readonly_first",
            "dry_run_before_real",
            "preview_token_before_place",
            "tiny_order_only",
            "track_every_order",
            "reconcile_after_attempt",
            "auto_lock_after_finish",
            "final_report_required",
        ],
        "generated_at": now_iso(),
    }


def build_pilot_rehearsal_checklist(data: dict, settings: dict) -> dict:
    runbook = build_live_micro_pilot_runbook(data, settings)
    checklist = []
    for step in REV36_STEPS:
        phase = next((p for p in runbook["phases"] if p["phase_id"] == step["id"]), {})
        checklist.append({
            "step_id": step["id"],
            "order": step["order"],
            "title": step["title"],
            "endpoint": step["endpoint"],
            "required": step["required"],
            "status": phase.get("status", "ready"),
            "blockers": phase.get("blockers", []),
            "warnings": phase.get("warnings", []),
        })
    ready_count = len([x for x in checklist if x["status"] == "ready"])
    return {
        "status": "ready" if ready_count == len(checklist) else "blocked",
        "checklist": checklist,
        "ready_count": ready_count,
        "total_count": len(checklist),
        "runbook_status": runbook.get("status"),
        "generated_at": now_iso(),
    }


def record_pilot_rehearsal(data: dict, settings: dict, user: str, payload: dict | None = None) -> dict:
    state = ensure_real_trade_state(data)
    checklist = build_pilot_rehearsal_checklist(data, settings)
    item = {
        "id": f"rev36_rehearsal_{uuid4().hex[:12]}",
        "created_at": now_iso(),
        "created_by": user,
        "status": checklist["status"],
        "checklist": checklist["checklist"],
        "note": str((payload or {}).get("note") or "manual_rehearsal"),
        "paper_only": True,
        "real_order_executed": False,
    }
    state.setdefault("pilot", {}).setdefault("rehearsals", []).append(item)
    state["pilot"]["rehearsals"] = state["pilot"]["rehearsals"][-50:]
    append_audit(data, "real_pilot.rehearsal", item["status"], "Rev36 mikro pilot prova checklisti üretildi.", meta={"category": "trading", "severity": "notice", "endpoint": "/api/real/pilot/rehearsal", "rehearsal_id": item["id"], "status": item["status"]}, user=user)
    return {"status": item["status"], "rehearsal": item, "checklist": checklist}


def build_tiny_order_plan(data: dict, settings: dict, order: dict | None = None) -> dict:
    state = ensure_real_trade_state(data)
    cfg = pilot_config()
    payload = _safe_order_payload(order, cfg)
    blockers: list[str] = []
    warnings: list[str] = []
    if payload["symbol"] not in set(cfg.get("allowed_symbols") or []):
        blockers.append("symbol_not_allowed_for_pilot")
    if payload["quote_order_qty"] <= 0:
        blockers.append("invalid_quote_order_qty")
    if payload["quote_order_qty"] > float(cfg.get("max_order_usdt") or 5):
        blockers.append("quote_order_qty_exceeds_pilot_max")
    if len(open_real_positions(state)) >= int(cfg.get("max_open_positions") or 1):
        blockers.append("pilot_max_open_positions_reached")
    if not state.get("owner_unlocked"):
        warnings.append("owner_unlock_required_before_place")
    plan = {
        "status": "blocked" if blockers else "planned",
        "payload": payload,
        "blockers": sorted(set(blockers)),
        "warnings": sorted(set(warnings)),
        "sequence": [
            "GET /api/real/readiness",
            "POST /api/real/orders/dry-run",
            "POST /api/real/orders/preview",
            "POST /api/real/unlock",
            "POST /api/real/orders/place",
            "GET /api/real/positions/lifecycle",
            "POST /api/real/positions/reconcile",
            "POST /api/real/pilot/finalize",
            "GET /api/real/pilot/report",
        ],
        "hard_limits": {
            "max_order_usdt": cfg.get("max_order_usdt"),
            "max_open_positions": cfg.get("max_open_positions"),
            "max_daily_trades": cfg.get("max_daily_trades"),
            "daily_loss_limit_usdt": cfg.get("daily_loss_limit_usdt"),
        },
        "real_order_executed_by_this_endpoint": False,
        "generated_at": now_iso(),
    }
    return plan


def finalize_pilot_procedure(data: dict, settings: dict, user: str, reason: str = "rev36_finalize") -> dict:
    state = ensure_real_trade_state(data)
    before_pilot = dict(state.get("pilot") or {})
    reconcile = reconcile_real_positions(data, settings)
    report = build_pilot_report(data, settings)
    lock_real_trading(state, reason)
    pilot = state.setdefault("pilot", {})
    pilot["active"] = False
    pilot["status"] = "finalized_auto_locked"
    pilot["finalized_at"] = now_iso()
    final_report = {
        "status": "ok",
        "reason": reason,
        "before_pilot": before_pilot,
        "pilot": pilot,
        "reconciliation": reconcile,
        "report": report,
        "real_lock_reason": state.get("lock_reason"),
        "owner_unlocked": bool(state.get("owner_unlocked")),
        "finalized_at": pilot["finalized_at"],
    }
    pilot["rev36_final_report"] = final_report
    append_audit(data, "real_pilot.finalize", "ok", "Rev36 pilot prosedürü finalize edildi ve real trading kilitlendi.", meta={"category": "trading", "severity": "critical", "endpoint": "/api/real/pilot/finalize", "reason": reason}, user=user)
    return final_report


def build_revision_36_quality_report(data: dict, settings: dict) -> dict:
    runbook = build_live_micro_pilot_runbook(data, settings)
    checklist = build_pilot_rehearsal_checklist(data, settings)
    tiny_plan = build_tiny_order_plan(data, settings, None)
    checks = {
        "readonly_to_report_runbook": len(runbook.get("procedure") or []) == 8,
        "dry_run_before_real_order": "POST /api/real/orders/dry-run" in tiny_plan.get("sequence", []) and tiny_plan["sequence"].index("POST /api/real/orders/dry-run") < tiny_plan["sequence"].index("POST /api/real/orders/place"),
        "preview_token_before_place": "POST /api/real/orders/preview" in tiny_plan.get("sequence", []) and tiny_plan["sequence"].index("POST /api/real/orders/preview") < tiny_plan["sequence"].index("POST /api/real/orders/place"),
        "reconcile_after_place": tiny_plan["sequence"].index("POST /api/real/positions/reconcile") > tiny_plan["sequence"].index("POST /api/real/orders/place"),
        "auto_lock_after_finish": "POST /api/real/pilot/finalize" in tiny_plan.get("sequence", []),
        "final_report_required": "GET /api/real/pilot/report" in tiny_plan.get("sequence", []),
        "tiny_order_limited": float((tiny_plan.get("hard_limits") or {}).get("max_order_usdt") or 0) <= 10,
        "procedure_endpoint_is_non_executing": tiny_plan.get("real_order_executed_by_this_endpoint") is False,
    }
    score = round(100 * sum(1 for ok in checks.values() if ok) / max(1, len(checks)), 2)
    return {
        "status": "ok" if all(checks.values()) else "review",
        "revision": 36,
        "readiness_score": score,
        "checks": checks,
        "runbook": runbook,
        "rehearsal_checklist": checklist,
        "tiny_order_plan": tiny_plan,
        "generated_at": now_iso(),
    }
