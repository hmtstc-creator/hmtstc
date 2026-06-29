from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from core.auth import require_owner, require_user
from core.config import DEFAULT_USER
from core.storage import load_settings, load_shadow, save_shadow
from services.real_trade_service import (
    build_binance_health,
    build_order_safety_report,
    build_real_readiness,
    build_real_lifecycle,
    build_real_position_timeline,
    detect_real_position_orphans,
    build_real_wallet_integrity,
    build_real_money_separation,
    build_real_pnl,
    build_manual_reconciliation,
    capture_real_balance_snapshot,
    dry_run_order,
    emergency_close_preview,
    owner_lock,
    owner_unlock,
    place_real_order,
    read_real_balances,
    reconcile_real_positions,
    transition_real_position,
)
from services.real_trade_state_service import ensure_real_trade_state
from services.emergency_recovery_service import (
    build_emergency_close_preview_v2,
    build_emergency_close_preview_final,
    execute_emergency_close,
    build_emergency_visibility,
    build_emergency_recovery_status,
    build_recovery_checklist,
    trigger_emergency_lock,
    unlock_recovery_mode,
)
from services.real_pilot_service import (
    build_pilot_report,
    build_pilot_visibility,
    ensure_pilot_state,
    finalize_pilot_controller,
    pilot_config,
    pilot_readiness,
    record_pilot_order_attempt,
    start_pilot,
    stop_pilot,
    validate_pilot_order_guard,
)
from contracts.real import OrderPlaceRequest, OrderPreviewRequest
from services.live_micro_pilot_procedure_service import (
    build_live_micro_pilot_runbook,
    build_pilot_rehearsal_checklist,
    build_tiny_order_plan,
    finalize_pilot_procedure,
    record_pilot_rehearsal,
)

router = APIRouter(prefix="/api/real", tags=["real-trade"])


def current_username(current_user: dict) -> str:
    username = str(current_user.get("username") or "").strip()
    return username or DEFAULT_USER


@router.get("/health")
def real_health(current_user: dict = Depends(require_user)):
    return build_binance_health()


@router.get("/readiness")
def real_readiness(current_user: dict = Depends(require_user)):
    user = current_username(current_user)
    data = load_shadow(user)
    settings = load_settings(user)
    payload = build_real_readiness(data, settings)
    save_shadow(data, user)
    return payload


@router.get("/account")
def real_account(current_user: dict = Depends(require_owner)):
    return build_binance_health()


@router.get("/balances")
def real_balances(current_user: dict = Depends(require_owner)):
    return read_real_balances()


@router.get("/positions")
def real_positions(current_user: dict = Depends(require_owner)):
    user = current_username(current_user)
    data = load_shadow(user)
    state = ensure_real_trade_state(data)
    return {"status": "ok", "positions": state.get("positions", []), "count": len(state.get("positions", []) or [])}




@router.get("/positions/lifecycle")
def real_positions_lifecycle(current_user: dict = Depends(require_owner)):
    user = current_username(current_user)
    data = load_shadow(user)
    settings = load_settings(user)
    payload = build_real_lifecycle(data, settings)
    save_shadow(data, user)
    return payload


@router.get("/positions/{position_id}/timeline")
def real_position_timeline(position_id: str, current_user: dict = Depends(require_owner)):
    user = current_username(current_user)
    data = load_shadow(user)
    payload = build_real_position_timeline(data, position_id)
    return payload


@router.get("/positions/orphans")
def real_position_orphans(current_user: dict = Depends(require_owner)):
    user = current_username(current_user)
    data = load_shadow(user)
    payload = detect_real_position_orphans(data, create_markers=False)
    return payload


@router.post("/positions/orphans/mark")
def real_position_orphans_mark(current_user: dict = Depends(require_owner)):
    user = current_username(current_user)
    data = load_shadow(user)
    payload = detect_real_position_orphans(data, create_markers=True)
    save_shadow(data, user)
    return payload


@router.post("/positions/transition")
def real_positions_transition(payload: dict, current_user: dict = Depends(require_owner)):
    user = current_username(current_user)
    data = load_shadow(user)
    position_id = str((payload or {}).get("position_id") or "")
    to_status = str((payload or {}).get("to_status") or "")
    reason = str((payload or {}).get("reason") or "manual_ui_transition")
    result = transition_real_position(data, position_id, to_status, reason=reason, meta={"endpoint": "/api/real/positions/transition"}, user=user)
    save_shadow(data, user)
    if result.get("status") == "blocked":
        raise HTTPException(status_code=400, detail={"code": "REAL_POSITION_TRANSITION_BLOCKED", "message": "Real position lifecycle transition engellendi.", "result": result})
    return result



@router.get("/wallet-integrity")
def real_wallet_integrity(current_user: dict = Depends(require_owner)):
    user = current_username(current_user)
    data = load_shadow(user)
    settings = load_settings(user)
    payload = build_real_wallet_integrity(data, settings)
    save_shadow(data, user)
    return payload


@router.get("/money-separation")
def real_money_separation(current_user: dict = Depends(require_user)):
    user = current_username(current_user)
    data = load_shadow(user)
    settings = load_settings(user)
    return build_real_money_separation(data, settings)


@router.get("/balances/reconciliation")
def real_balance_reconciliation_status(current_user: dict = Depends(require_owner)):
    user = current_username(current_user)
    data = load_shadow(user)
    state = ensure_real_trade_state(data)
    return state.get("last_balance_reconciliation") or {"status": "not_run", "message": "Henüz reconciliation çalışmadı."}



@router.get("/reconciliation/report")
def real_reconciliation_report(current_user: dict = Depends(require_owner)):
    user = current_username(current_user)
    data = load_shadow(user)
    settings = load_settings(user)
    payload = reconcile_real_positions(data, settings)
    save_shadow(data, user)
    return payload


@router.get("/reconciliation/manual")
def real_reconciliation_manual_report(current_user: dict = Depends(require_owner)):
    user = current_username(current_user)
    data = load_shadow(user)
    settings = load_settings(user)
    payload = build_manual_reconciliation(data, settings)
    save_shadow(data, user)
    return payload


@router.get("/reconciliation/pnl")
def real_reconciliation_pnl(current_user: dict = Depends(require_owner)):
    user = current_username(current_user)
    data = load_shadow(user)
    settings = load_settings(user)
    payload = build_real_pnl(data, settings)
    save_shadow(data, user)
    return payload


@router.post("/reconciliation/snapshot")
def real_reconciliation_snapshot(payload: dict | None = None, current_user: dict = Depends(require_owner)):
    user = current_username(current_user)
    data = load_shadow(user)
    phase = str((payload or {}).get("phase") or "manual")
    order = (payload or {}).get("order") if isinstance(payload, dict) else None
    reason = str((payload or {}).get("reason") or "manual_balance_snapshot")
    result = capture_real_balance_snapshot(data, phase=phase, order=order or {}, reason=reason)
    save_shadow(data, user)
    return result

@router.post("/positions/reconcile")
def real_positions_reconcile(current_user: dict = Depends(require_owner)):
    user = current_username(current_user)
    data = load_shadow(user)
    settings = load_settings(user)
    payload = reconcile_real_positions(data, settings)
    save_shadow(data, user)
    return payload


@router.post("/positions/emergency-close")
def real_positions_emergency_close(current_user: dict = Depends(require_owner)):
    user = current_username(current_user)
    data = load_shadow(user)
    settings = load_settings(user)
    payload = build_emergency_close_preview_v2(data, settings, user=user)
    save_shadow(data, user)
    return payload


@router.get("/emergency/recovery")
def real_emergency_recovery_status(current_user: dict = Depends(require_owner)):
    user = current_username(current_user)
    data = load_shadow(user)
    settings = load_settings(user)
    payload = build_emergency_recovery_status(data, settings)
    save_shadow(data, user)
    return payload


@router.get("/emergency/checklist")
def real_emergency_recovery_checklist(current_user: dict = Depends(require_owner)):
    user = current_username(current_user)
    data = load_shadow(user)
    settings = load_settings(user)
    payload = build_recovery_checklist(data, settings)
    save_shadow(data, user)
    return payload


@router.post("/emergency/lock")
def real_emergency_lock(payload: dict | None = None, current_user: dict = Depends(require_owner)):
    user = current_username(current_user)
    data = load_shadow(user)
    reason = str((payload or {}).get("reason") or "manual_emergency_lock")
    result = trigger_emergency_lock(data, user=user, reason=reason)
    save_shadow(data, user)
    return result


@router.post("/emergency/recovery-unlock")
def real_emergency_recovery_unlock(payload: dict | None = None, current_user: dict = Depends(require_owner)):
    user = current_username(current_user)
    data = load_shadow(user)
    reason = str((payload or {}).get("reason") or "manual_recovery_unlock")
    result = unlock_recovery_mode(data, user=user, reason=reason)
    save_shadow(data, user)
    if result.get("status") == "blocked":
        raise HTTPException(status_code=400, detail={"code": "EMERGENCY_RECOVERY_BLOCKED", "message": "Recovery unlock checklist nedeniyle engellendi.", "blockers": result.get("blockers", [])})
    return result




@router.get("/emergency/visibility")
def real_emergency_visibility(current_user: dict = Depends(require_user)):
    user = current_username(current_user)
    data = load_shadow(user)
    settings = load_settings(user)
    payload = build_emergency_visibility(data, settings)
    save_shadow(data, user)
    return payload


@router.post("/emergency/close")
def real_emergency_close_execute(payload: dict | None = None, current_user: dict = Depends(require_owner)):
    user = current_username(current_user)
    data = load_shadow(user)
    settings = load_settings(user)
    result = execute_emergency_close(data, settings, payload or {}, user=user, role=str(current_user.get("role") or "owner"))
    save_shadow(data, user)
    if result.get("status") == "blocked":
        raise HTTPException(status_code=400, detail={"code": "EMERGENCY_CLOSE_BLOCKED", "message": "Emergency close engellendi.", "result": result})
    return result


@router.post("/emergency/close-preview")
def real_emergency_close_preview_v2(current_user: dict = Depends(require_owner)):
    user = current_username(current_user)
    data = load_shadow(user)
    settings = load_settings(user)
    payload = build_emergency_close_preview_final(data, settings, user=user, role=str(current_user.get("role") or "owner"))
    save_shadow(data, user)
    return payload


@router.get("/orders")
def real_orders(current_user: dict = Depends(require_owner)):
    user = current_username(current_user)
    data = load_shadow(user)
    state = ensure_real_trade_state(data)
    return {"status": "ok", "orders": state.get("orders", [])[-200:], "count": len(state.get("orders", []) or [])}


@router.post("/orders/preview")
def real_order_preview(order: OrderPreviewRequest, current_user: dict = Depends(require_owner)):
    user = current_username(current_user)
    data = load_shadow(user)
    settings = load_settings(user)
    order_payload = order.dict(exclude_none=True)
    payload = build_order_safety_report(data, settings, order_payload, user=user, role=str(current_user.get("role") or "owner"))
    save_shadow(data, user)
    return payload


@router.post("/orders/dry-run")
def real_order_dry_run(order: OrderPreviewRequest, current_user: dict = Depends(require_owner)):
    user = current_username(current_user)
    data = load_shadow(user)
    settings = load_settings(user)
    order_payload = order.dict(exclude_none=True)
    payload = dry_run_order(data, settings, order_payload, user=user, role=str(current_user.get("role") or "owner"))
    save_shadow(data, user)
    return payload


@router.post("/orders/place")
def real_order_place(order: OrderPlaceRequest, current_user: dict = Depends(require_owner)):
    user = current_username(current_user)
    data = load_shadow(user)
    settings = load_settings(user)
    order_payload = order.dict(exclude_none=True)
    payload = place_real_order(data, settings, order_payload, user=user, role=str(current_user.get("role") or "owner"))
    save_shadow(data, user)
    if payload.get("status") == "blocked":
        raise HTTPException(status_code=400, detail={"code": "REAL_ORDER_BLOCKED", "message": "Real order safety layer tarafından engellendi.", "blockers": payload.get("blockers", [])})
    return payload


@router.post("/unlock")
def real_unlock(payload: dict | None = None, current_user: dict = Depends(require_owner)):
    user = current_username(current_user)
    data = load_shadow(user)
    minutes = int((payload or {}).get("minutes") or 30)
    result = owner_unlock(data, user, minutes)
    save_shadow(data, user)
    return result


@router.post("/lock")
def real_lock(payload: dict | None = None, current_user: dict = Depends(require_owner)):
    user = current_username(current_user)
    data = load_shadow(user)
    result = owner_lock(data, user, reason=str((payload or {}).get("reason") or "manual_lock"))
    save_shadow(data, user)
    return result


@router.get("/pilot")
def real_pilot_status(current_user: dict = Depends(require_owner)):
    user = current_username(current_user)
    data = load_shadow(user)
    settings = load_settings(user)
    pilot = ensure_pilot_state(data)
    payload = {"status": "ok", "pilot": pilot, "config": pilot_config(), "readiness": pilot_readiness(data, settings)}
    save_shadow(data, user)
    return payload


@router.get("/pilot/readiness")
def real_pilot_readiness(current_user: dict = Depends(require_owner)):
    user = current_username(current_user)
    data = load_shadow(user)
    settings = load_settings(user)
    payload = pilot_readiness(data, settings)
    save_shadow(data, user)
    return payload


@router.get("/pilot/config")
def real_pilot_config(current_user: dict = Depends(require_owner)):
    return {"status": "ok", "config": pilot_config()}


@router.post("/pilot/start")
def real_pilot_start(payload: dict | None = None, current_user: dict = Depends(require_owner)):
    user = current_username(current_user)
    data = load_shadow(user)
    settings = load_settings(user)
    minutes = int((payload or {}).get("minutes") or 0) or None
    result = start_pilot(data, settings, user=user, minutes=minutes)
    save_shadow(data, user)
    if result.get("status") == "blocked":
        raise HTTPException(status_code=400, detail={"code": "REAL_PILOT_BLOCKED", "message": "Mikro pilot readiness kapıları nedeniyle başlatılamadı.", "blockers": result.get("blockers", [])})
    return result


@router.post("/pilot/stop")
def real_pilot_stop(payload: dict | None = None, current_user: dict = Depends(require_owner)):
    user = current_username(current_user)
    data = load_shadow(user)
    reason = str((payload or {}).get("reason") or "manual_stop")
    settings = load_settings(user)
    result = stop_pilot(data, user=user, reason=reason, settings=settings)
    save_shadow(data, user)
    return result


@router.get("/pilot/report")
def real_pilot_report(current_user: dict = Depends(require_owner)):
    user = current_username(current_user)
    data = load_shadow(user)
    settings = load_settings(user)
    payload = build_pilot_report(data, settings)
    save_shadow(data, user)
    return payload




@router.get("/pilot/visibility")
def real_pilot_visibility(current_user: dict = Depends(require_user)):
    user = current_username(current_user)
    data = load_shadow(user)
    settings = load_settings(user)
    payload = build_pilot_visibility(data, settings)
    save_shadow(data, user)
    return payload


@router.post("/pilot/order-guard")
def real_pilot_order_guard(payload: dict | None = None, current_user: dict = Depends(require_owner)):
    user = current_username(current_user)
    data = load_shadow(user)
    result = validate_pilot_order_guard(data, payload or {})
    save_shadow(data, user)
    if result.get("status") == "blocked":
        raise HTTPException(status_code=400, detail={"code": "REAL_PILOT_ORDER_BLOCKED", "blockers": result.get("blockers", [])})
    return result


@router.post("/pilot/order-attempt")
def real_pilot_order_attempt(payload: dict | None = None, current_user: dict = Depends(require_owner)):
    user = current_username(current_user)
    data = load_shadow(user)
    result = record_pilot_order_attempt(data, payload or {}, status=str((payload or {}).get("status") or "attempt"), user=user)
    save_shadow(data, user)
    if result.get("status") == "blocked":
        raise HTTPException(status_code=400, detail={"code": "REAL_PILOT_ORDER_BLOCKED", "blockers": result.get("guard", {}).get("blockers", [])})
    return result


@router.post("/pilot/final-report")
def real_pilot_final_report(payload: dict | None = None, current_user: dict = Depends(require_owner)):
    user = current_username(current_user)
    data = load_shadow(user)
    settings = load_settings(user)
    reason = str((payload or {}).get("reason") or "final_report")
    result = finalize_pilot_controller(data, settings=settings, user=user, reason=reason)
    save_shadow(data, user)
    return result


@router.get("/pilot/procedure")
def real_pilot_procedure(current_user: dict = Depends(require_owner)):
    user = current_username(current_user)
    data = load_shadow(user)
    settings = load_settings(user)
    payload = build_live_micro_pilot_runbook(data, settings)
    save_shadow(data, user)
    return payload


@router.get("/pilot/runbook")
def real_pilot_runbook(current_user: dict = Depends(require_owner)):
    user = current_username(current_user)
    data = load_shadow(user)
    settings = load_settings(user)
    payload = build_live_micro_pilot_runbook(data, settings)
    save_shadow(data, user)
    return payload


@router.post("/pilot/rehearsal")
def real_pilot_rehearsal(payload: dict | None = None, current_user: dict = Depends(require_owner)):
    user = current_username(current_user)
    data = load_shadow(user)
    settings = load_settings(user)
    result = record_pilot_rehearsal(data, settings, user=user, payload=payload)
    save_shadow(data, user)
    return result


@router.post("/pilot/tiny-order-plan")
def real_pilot_tiny_order_plan(payload: dict | None = None, current_user: dict = Depends(require_owner)):
    user = current_username(current_user)
    data = load_shadow(user)
    settings = load_settings(user)
    result = build_tiny_order_plan(data, settings, payload or {})
    save_shadow(data, user)
    return result


@router.post("/pilot/finalize")
def real_pilot_finalize(payload: dict | None = None, current_user: dict = Depends(require_owner)):
    user = current_username(current_user)
    data = load_shadow(user)
    settings = load_settings(user)
    reason = str((payload or {}).get("reason") or "rev36_live_micro_pilot_finalize")
    result = finalize_pilot_procedure(data, settings, user=user, reason=reason)
    save_shadow(data, user)
    return result
