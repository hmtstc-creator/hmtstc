from __future__ import annotations

from datetime import datetime, timedelta
from uuid import uuid4
import hashlib

from core.storage import append_audit, now_iso
from services.real_position_lifecycle_service import OPEN_LIFECYCLE_STATUSES, build_emergency_close_lifecycle_preview, ensure_position_lifecycles, transition_position
from services.real_trade_state_service import ensure_real_trade_state, lock_real_trading, open_real_positions, create_confirmation_token, consume_confirmation_token, is_unlock_valid
from services.real_pilot_service import stop_pilot


def _parse_dt(value: str | None):
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace('Z', '+00:00'))
    except Exception:
        return None


def ensure_emergency_state(data: dict) -> dict:
    state = ensure_real_trade_state(data)
    emergency = state.setdefault('emergency_recovery', {})
    emergency.setdefault('lock_active', bool(state.get('emergency_lock')))
    emergency.setdefault('locked_at', state.get('emergency_locked_at'))
    emergency.setdefault('locked_by', state.get('emergency_locked_by'))
    emergency.setdefault('lock_reason', state.get('emergency_reason') or state.get('lock_reason'))
    emergency.setdefault('last_preview', None)
    emergency.setdefault('last_recovery_checklist', None)
    emergency.setdefault('timeline', [])
    emergency['timeline'] = (emergency.get('timeline') or [])[-300:]
    return emergency


def append_emergency_event(data: dict, action: str, result: str, message: str, meta: dict | None = None, user: str = 'system') -> dict:
    state = ensure_real_trade_state(data)
    emergency = ensure_emergency_state(data)
    item = {
        'id': f'emg_{uuid4().hex}',
        'at': now_iso(),
        'action': action,
        'result': result,
        'message': message,
        'meta': meta or {},
        'user': user,
    }
    emergency.setdefault('timeline', []).append(item)
    emergency['timeline'] = emergency['timeline'][-300:]
    state['last_emergency_event'] = item
    append_audit(
        data,
        action,
        result,
        message,
        meta={
            'category': 'trading',
            'severity': 'critical' if result in {'ok', 'preview'} else 'blocked',
            'endpoint': (meta or {}).get('endpoint'),
            'emergency': True,
            **(meta or {}),
        },
        user=user,
    )
    return item


def trigger_emergency_lock(data: dict, user: str = 'system', reason: str = 'manual_emergency_stop') -> dict:
    state = ensure_real_trade_state(data)
    lock_real_trading(state, reason=reason)
    state['emergency_lock'] = True
    state['emergency_locked_at'] = now_iso()
    state['emergency_locked_by'] = user
    state['emergency_reason'] = reason
    state.setdefault('pilot', {})['active'] = False
    emergency = ensure_emergency_state(data)
    emergency['lock_active'] = True
    emergency['locked_at'] = state['emergency_locked_at']
    emergency['locked_by'] = user
    emergency['lock_reason'] = reason
    append_emergency_event(data, 'emergency.lock', 'ok', 'Emergency lock aktif edildi; real trading ve mikro pilot güvenli moda alındı.', {'reason': reason, 'endpoint': '/api/real/emergency/lock'}, user=user)
    return build_emergency_recovery_status(data)


def build_emergency_recovery_status(data: dict, settings: dict | None = None) -> dict:
    state = ensure_real_trade_state(data)
    emergency = ensure_emergency_state(data)
    ensure_position_lifecycles(data)
    open_positions = open_real_positions(state)
    manual = [p for p in open_positions if p.get('manual_attention_required') or str(p.get('status')) == 'manual_attention_required']
    blockers = []
    warnings = []
    if state.get('emergency_lock') or emergency.get('lock_active'):
        blockers.append('emergency_lock_active')
    if state.get('owner_unlocked'):
        warnings.append('owner_unlock_should_be_closed_during_emergency')
    if state.get('pilot', {}).get('active'):
        warnings.append('pilot_should_be_stopped_during_emergency')
    if open_positions:
        warnings.append('open_real_positions_require_review')
    if manual:
        blockers.append('manual_attention_positions_present')
    checklist = build_recovery_checklist(data, settings or {})
    return {
        'status': 'blocked' if blockers else ('review' if warnings else 'ok'),
        'lock_active': bool(state.get('emergency_lock') or emergency.get('lock_active')),
        'locked_at': emergency.get('locked_at'),
        'locked_by': emergency.get('locked_by'),
        'lock_reason': emergency.get('lock_reason'),
        'owner_unlocked': bool(state.get('owner_unlocked')),
        'pilot_active': bool(state.get('pilot', {}).get('active')),
        'open_real_positions': len(open_positions),
        'manual_attention_count': len(manual),
        'blockers': blockers,
        'warnings': warnings,
        'checklist': checklist,
        'last_preview': emergency.get('last_preview'),
        'timeline': (emergency.get('timeline') or [])[-50:],
        'message': 'Emergency recovery gerçek emir üretmez; owner kontrolünde risk/checklist doğrulaması sağlar.',
    }


def build_recovery_checklist(data: dict, settings: dict | None = None) -> dict:
    state = ensure_real_trade_state(data)
    ensure_position_lifecycles(data)
    open_positions = open_real_positions(state)
    last_rec = state.get('last_balance_reconciliation') or state.get('last_reconciliation') or {}
    wallet = state.get('last_wallet_integrity') or {}
    items = [
        {'key': 'real_trading_locked', 'label': 'Real trading locked', 'ok': not state.get('owner_unlocked')},
        {'key': 'pilot_stopped', 'label': 'Micro pilot stopped', 'ok': not state.get('pilot', {}).get('active')},
        {'key': 'open_positions_reviewed', 'label': 'Open real positions reviewed', 'ok': len(open_positions) == 0, 'count': len(open_positions)},
        {'key': 'balance_reconciliation_recent', 'label': 'Balance reconciliation available', 'ok': bool(last_rec), 'status': last_rec.get('status')},
        {'key': 'wallet_integrity_available', 'label': 'Wallet integrity available', 'ok': bool(wallet), 'status': wallet.get('status')},
        {'key': 'manual_attention_clear', 'label': 'Manual attention clear', 'ok': not state.get('manual_attention_required')},
        {'key': 'emergency_close_preview_available', 'label': 'Emergency close preview generated', 'ok': bool(state.get('emergency_recovery', {}).get('last_preview'))},
        {'key': 'owner_unlock_closed', 'label': 'Owner unlock closed', 'ok': not state.get('owner_unlocked')},
    ]
    score = round(sum(1 for item in items if item.get('ok')) / max(1, len(items)) * 100, 2)
    checklist = {'status': 'ok' if score >= 80 else 'review', 'score': score, 'items': items, 'generated_at': now_iso()}
    ensure_emergency_state(data)['last_recovery_checklist'] = checklist
    return checklist


def build_emergency_close_preview_v2(data: dict, settings: dict | None = None, user: str = 'system') -> dict:
    state = ensure_real_trade_state(data)
    base = build_emergency_close_lifecycle_preview(data)
    positions = base.get('positions') or base.get('items') or []
    enhanced = []
    for item in positions:
        symbol = str(item.get('symbol') or '').upper()
        side = 'SELL' if str(item.get('side') or 'BUY').upper() == 'BUY' else 'BUY'
        quantity = item.get('quantity') or item.get('executed_qty') or item.get('orig_qty') or item.get('quote_order_qty')
        enhanced.append({
            **item,
            'close_side': side,
            'quantity_to_close': quantity,
            'requires_owner_confirmation': True,
            'requires_dry_run_preview': True,
            'requires_confirmation_token': True,
            'will_send_order': False,
            'symbol_filter_validation_required': True,
            'manual_attention_if_failed': True,
        })
    preview = {
        'status': 'preview' if enhanced else 'empty',
        'generated_at': now_iso(),
        'positions_count': len(enhanced),
        'positions': enhanced,
        'policy': {
            'auto_close': False,
            'owner_only': True,
            'double_confirmation_required': True,
            'dry_run_before_real_close': True,
            'real_order_requires_token': True,
        },
        'message': 'Rev23 emergency close sadece lifecycle-aware preview üretir; gerçek emir göndermez.',
    }
    emergency = ensure_emergency_state(data)
    emergency['last_preview'] = preview
    state['last_emergency_close_preview'] = preview
    append_emergency_event(data, 'emergency.close_preview', 'preview', 'Emergency close lifecycle-aware preview üretildi.', {'positions_count': len(enhanced), 'endpoint': '/api/real/emergency/close-preview'}, user=user)
    return preview


def unlock_recovery_mode(data: dict, user: str = 'system', reason: str = 'manual_recovery_unlock') -> dict:
    state = ensure_real_trade_state(data)
    checklist = build_recovery_checklist(data, {})
    blockers = []
    if checklist.get('score', 0) < 80:
        blockers.append('recovery_checklist_score_below_80')
    if open_real_positions(state):
        blockers.append('open_positions_exist_preview_required')
    if blockers:
        append_emergency_event(data, 'emergency.recovery_unlock_blocked', 'blocked', 'Emergency recovery unlock engellendi.', {'blockers': blockers, 'checklist': checklist, 'endpoint': '/api/real/emergency/recovery-unlock'}, user=user)
        return {'status': 'blocked', 'blockers': blockers, 'checklist': checklist}
    state['emergency_lock'] = False
    emergency = ensure_emergency_state(data)
    emergency['lock_active'] = False
    emergency['unlocked_at'] = now_iso()
    emergency['unlocked_by'] = user
    emergency['unlock_reason'] = reason
    # Recovery unlock never starts pilot or owner real trading unlock.
    state['owner_unlocked'] = False
    state['unlock_expires_at'] = None
    state.setdefault('pilot', {})['active'] = False
    append_emergency_event(data, 'emergency.recovery_unlock', 'ok', 'Emergency recovery kilidi kaldırıldı; real trading hâlâ owner unlock gerektirir.', {'reason': reason, 'checklist': checklist, 'endpoint': '/api/real/emergency/recovery-unlock'}, user=user)
    return build_emergency_recovery_status(data)


# ---------------------------------------------------------------------------
# Level1 Rev44 - Emergency Close & Recovery final contract
# ---------------------------------------------------------------------------

def _safe_float(value, fallback: float = 0.0) -> float:
    try:
        if value is None or value == "":
            return fallback
        return float(str(value).replace(",", "."))
    except Exception:
        return fallback


def _emergency_preview_id() -> str:
    return f"emg_preview_{uuid4().hex}"


def _emergency_payload(preview: dict, user: str = "system", role: str = "owner") -> dict:
    positions = preview.get("positions") or []
    qty_sum = sum(_safe_float(item.get("quantity_to_close") or item.get("quantity"), 0.0) for item in positions if isinstance(item, dict))
    preview_id = str(preview.get("preview_id") or _emergency_preview_id())
    return {
        "symbol": "EMERGENCY_CLOSE",
        "side": "CLOSE",
        "quote_order_qty": str(qty_sum or len(positions)),
        "preview_id": preview_id,
        "user": user,
        "role": role,
    }


def build_emergency_close_preview_final(data: dict, settings: dict | None = None, user: str = "system", role: str = "owner") -> dict:
    """Build a final emergency close preview.

    This is read/prepare only. It never sends a Binance order. It creates a
    payload-bound confirmation token for a subsequent close request and stores
    a non-sensitive evidence snapshot in the real trade state.
    """
    state = ensure_real_trade_state(data)
    base = build_emergency_close_preview_v2(data, settings or {}, user=user)
    preview_id = str(base.get("preview_id") or _emergency_preview_id())
    positions = []
    estimated_fee = 0.0
    estimated_loss = 0.0
    for item in base.get("positions") or []:
        if not isinstance(item, dict):
            continue
        qty = _safe_float(item.get("quantity_to_close") or item.get("quantity"), 0.0)
        notional = _safe_float(item.get("quote_order_qty") or item.get("notional") or item.get("usdt_size"), 0.0)
        fee = round(max(notional, qty) * 0.001, 8)
        estimated_fee += fee
        estimated_loss += max(0.0, _safe_float(item.get("unrealized_pnl"), 0.0) * -1)
        positions.append({
            **item,
            "quantity_to_close": qty or item.get("quantity_to_close"),
            "estimated_fee_usdt": fee,
            "estimated_loss_usdt": round(max(0.0, _safe_float(item.get("unrealized_pnl"), 0.0) * -1), 8),
            "preview_id": preview_id,
        })
    payload = _emergency_payload({"positions": positions, "preview_id": preview_id}, user=user, role=role)
    token = create_confirmation_token(state, payload, ttl_seconds=60, user=user, role=role, preview_id=preview_id)
    preview = {
        "status": "preview" if positions else "empty",
        "preview_id": preview_id,
        "generated_at": now_iso(),
        "positions_count": len(positions),
        "positions": positions,
        "estimated_fee_usdt": round(estimated_fee, 8),
        "estimated_loss_usdt": round(estimated_loss, 8),
        "confirmation_token": token.get("token"),
        "confirmation_token_id": token.get("token_id"),
        "confirmation_expires_at": token.get("expires_at"),
        "confirmation_payload_hash": token.get("payload_hash"),
        "policy": {
            "auto_close": False,
            "owner_only": True,
            "double_confirmation_required": True,
            "ttl_seconds": 60,
            "single_use_token": True,
            "payload_bound_token": True,
            "dry_run_before_real_close": True,
            "real_trading_locked_after_close": True,
            "no_auto_start_after_recovery": True,
        },
        "will_send_order": False,
        "message": "Emergency close preview generated. No order was sent.",
    }
    emergency = ensure_emergency_state(data)
    emergency["last_preview"] = preview
    emergency["last_preview_id"] = preview_id
    state["last_emergency_close_preview"] = preview
    append_emergency_event(data, "emergency.close_preview_final", "preview", "Final emergency close preview ve confirmation token üretildi.", {"preview_id": preview_id, "positions_count": len(positions), "endpoint": "/api/real/emergency/close-preview"}, user=user)
    return preview


def execute_emergency_close(data: dict, settings: dict | None = None, payload: dict | None = None, user: str = "system", role: str = "owner") -> dict:
    """Execute an emergency close workflow.

    In dry-run mode this closes lifecycle records without sending real orders.
    In real mode it still requires owner unlock + explicit allow_real_execution;
    if not provided, it is blocked and manual attention is required. This keeps
    the package fail-safe while providing a complete state/audit contract.
    """
    payload = payload or {}
    state = ensure_real_trade_state(data)
    emergency = ensure_emergency_state(data)
    preview = emergency.get("last_preview") or state.get("last_emergency_close_preview") or build_emergency_close_preview_final(data, settings or {}, user=user, role=role)
    preview_id = str(payload.get("preview_id") or preview.get("preview_id") or emergency.get("last_preview_id") or "")
    token = str(payload.get("confirmation_token") or payload.get("token") or "")
    confirmation_payload = _emergency_payload({"positions": preview.get("positions") or [], "preview_id": preview_id}, user=user, role=role)
    confirmation = consume_confirmation_token(state, token, confirmation_payload, user=user, role=role, preview_id=preview_id)
    if not confirmation.get("ok"):
        append_emergency_event(data, "emergency.close_blocked", "blocked", "Emergency close confirmation token geçersiz.", {"reason": confirmation.get("reason"), "preview_id": preview_id, "endpoint": "/api/real/emergency/close"}, user=user)
        return {"status": "blocked", "reason": confirmation.get("reason"), "confirmation": confirmation, "preview_id": preview_id}

    runtime_dry_run = bool(state.get("dry_run", True))
    real_allowed = bool(payload.get("allow_real_execution")) and not runtime_dry_run and is_unlock_valid(state)
    if not runtime_dry_run and not real_allowed:
        state["manual_attention_required"] = True
        lock_real_trading(state, reason="emergency_close_real_mode_requires_explicit_owner_execution")
        append_emergency_event(data, "emergency.close_blocked", "blocked", "Real emergency close explicit owner execution olmadan engellendi.", {"preview_id": preview_id, "dry_run": runtime_dry_run}, user=user)
        return {"status": "blocked", "reason": "real_emergency_close_requires_explicit_owner_execution", "preview_id": preview_id, "manual_attention_required": True}

    ensure_position_lifecycles(data)
    closed = []
    failed = []
    for item in preview.get("positions") or []:
        position_id = str(item.get("position_id") or "")
        if not position_id:
            failed.append({"position_id": position_id, "reason": "missing_position_id"})
            continue
        req = transition_position(state, position_id, "closing_requested", reason="emergency_close_requested", meta={"preview_id": preview_id, "dry_run": runtime_dry_run}, actor=user)
        sub = transition_position(state, position_id, "closing_submitted", reason="emergency_close_submitted", meta={"preview_id": preview_id, "dry_run": runtime_dry_run, "real_order_created": bool(real_allowed)}, actor=user)
        if req.get("status") == "ok" or sub.get("status") == "ok":
            # In dry-run we complete the lifecycle for controlled testing. In real
            # mode this is a submitted state unless a downstream fill update moves it.
            target = "closed" if runtime_dry_run else "closing_submitted"
            final = transition_position(state, position_id, target, reason="emergency_close_dry_run_closed" if runtime_dry_run else "emergency_close_real_submitted", meta={"preview_id": preview_id, "dry_run": runtime_dry_run}, actor=user)
            if final.get("status") == "ok":
                closed.append({"position_id": position_id, "status": target, "dry_run": runtime_dry_run})
            else:
                failed.append({"position_id": position_id, "reason": final.get("reason"), "result": final})
        else:
            failed.append({"position_id": position_id, "reason": sub.get("reason") or req.get("reason"), "result": sub})
    if failed:
        state["manual_attention_required"] = True
        status = "partial" if closed else "failed"
    else:
        status = "dry_run_closed" if runtime_dry_run else "submitted"
    lock_real_trading(state, reason="emergency_close_completed_lock")
    state["emergency_lock"] = True
    emergency["lock_active"] = True
    emergency["last_close_result"] = {
        "status": status,
        "preview_id": preview_id,
        "closed": closed,
        "failed": failed,
        "dry_run": runtime_dry_run,
        "real_order_created": bool(real_allowed),
        "completed_at": now_iso(),
    }
    append_emergency_event(data, "emergency.close_execute", "ok" if not failed else "blocked", "Emergency close workflow tamamlandı; real trading kilitli kaldı.", {"preview_id": preview_id, "closed_count": len(closed), "failed_count": len(failed), "dry_run": runtime_dry_run, "endpoint": "/api/real/emergency/close"}, user=user)
    return emergency["last_close_result"]


def build_emergency_visibility(data: dict, settings: dict | None = None) -> dict:
    state = ensure_real_trade_state(data)
    emergency = ensure_emergency_state(data)
    status = build_emergency_recovery_status(data, settings or {})
    last_close = emergency.get("last_close_result") or {}
    return {
        "status": status.get("status"),
        "lock_active": bool(status.get("lock_active")),
        "open_real_positions": status.get("open_real_positions", 0),
        "manual_attention_required": bool(state.get("manual_attention_required") or status.get("manual_attention_count", 0)),
        "last_preview_id": emergency.get("last_preview_id"),
        "last_close_status": last_close.get("status") or "not_run",
        "closed_count": len(last_close.get("closed") or []),
        "failed_count": len(last_close.get("failed") or []),
        "no_auto_start": True,
        "owner_unlocked": bool(state.get("owner_unlocked")),
        "pilot_active": bool(state.get("pilot", {}).get("active")),
        "timeline_count": len(emergency.get("timeline") or []),
        "checked_at": now_iso(),
    }
