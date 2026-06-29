from __future__ import annotations

from services.emergency_recovery_service import build_emergency_close_preview_v2, build_emergency_recovery_status, build_recovery_checklist
from services.real_trade_state_service import ensure_real_trade_state


def _gate(name: str, status: str, message: str, details: dict | None = None) -> dict:
    return {'name': name, 'status': status, 'message': message, 'details': details or {}}


def build_emergency_recovery_quality(data: dict, settings: dict) -> dict:
    status = build_emergency_recovery_status(data, settings)
    gates = [
        _gate('emergency_lock_state', 'ok' if 'lock_active' in status else 'blocked', 'Emergency lock state okunabilir.', {'lock_active': status.get('lock_active')}),
        _gate('owner_unlock_closed_policy', 'ok' if not status.get('owner_unlocked') else 'review', 'Emergency modda owner unlock kapalı olmalıdır.', {'owner_unlocked': status.get('owner_unlocked')}),
        _gate('pilot_stop_policy', 'ok' if not status.get('pilot_active') else 'review', 'Emergency modda mikro pilot kapalı olmalıdır.', {'pilot_active': status.get('pilot_active')}),
        _gate('recovery_checklist', 'ok' if status.get('checklist', {}).get('items') else 'review', 'Recovery checklist üretildi.', status.get('checklist') or {}),
    ]
    blockers = [g for g in gates if g['status'] == 'blocked']
    return {'status': 'blocked' if blockers else 'ok', 'gates': gates, 'recovery': status}


def build_emergency_close_quality(data: dict, settings: dict) -> dict:
    state = ensure_real_trade_state(data)
    preview = state.get('last_emergency_close_preview') or build_emergency_close_preview_v2(data, settings)
    policy = preview.get('policy') or {}
    gates = [
        _gate('preview_available', 'ok' if preview else 'blocked', 'Emergency close preview üretilebilir.'),
        _gate('auto_close_disabled', 'ok' if policy.get('auto_close') is False else 'blocked', 'Rev23 otomatik emergency close göndermez.', policy),
        _gate('owner_only', 'ok' if policy.get('owner_only') else 'blocked', 'Emergency close owner-only olmalıdır.', policy),
        _gate('double_confirmation', 'ok' if policy.get('double_confirmation_required') else 'review', 'Çift onay politikası tanımlı.', policy),
        _gate('token_required', 'ok' if policy.get('real_order_requires_token') else 'review', 'Gerçek close için token gereksinimi tanımlı.', policy),
    ]
    blockers = [g for g in gates if g['status'] == 'blocked']
    return {'status': 'blocked' if blockers else 'ok', 'gates': gates, 'preview': preview}


def build_disaster_recovery_quality(data: dict, settings: dict) -> dict:
    state = ensure_real_trade_state(data)
    checklist = build_recovery_checklist(data, settings)
    gates = [
        _gate('real_trade_locks_on_recovery', 'ok' if not state.get('owner_unlocked') else 'review', 'Recovery sonrasında real trading otomatik başlamaz.'),
        _gate('pilot_locked_on_recovery', 'ok' if not state.get('pilot', {}).get('active') else 'review', 'Recovery sonrasında pilot kapalı kalır.'),
        _gate('checklist_scored', 'ok' if checklist.get('score') is not None else 'blocked', 'Checklist skor üretir.', checklist),
        _gate('manual_attention_tracked', 'ok' if 'manual_attention_required' in state else 'review', 'Manual attention state izlenir.', {'manual_attention_required': state.get('manual_attention_required')}),
    ]
    return {'status': 'ok' if not [g for g in gates if g['status'] == 'blocked'] else 'blocked', 'gates': gates, 'checklist': checklist}


def build_emergency_audit_timeline_quality(data: dict, settings: dict) -> dict:
    timeline = (ensure_real_trade_state(data).get('emergency_recovery') or {}).get('timeline') or []
    audit = data.get('audit') or data.get('audit_log') or []
    emergency_audit = [a for a in audit if 'emergency' in str(a.get('action') or '').lower()]
    return {
        'status': 'ok' if timeline is not None else 'review',
        'timeline_count': len(timeline),
        'audit_count': len(emergency_audit),
        'timeline': timeline[-30:],
        'message': 'Emergency timeline runtime state içinde, forensic audit ise audit log içinde izlenir.',
    }


def build_emergency_ui_contract(data: dict, settings: dict) -> dict:
    return {
        'status': 'ok',
        'required_panels': ['dashboard_emergency_recovery', 'positions_emergency_close_preview', 'intelligence_rev23_quality'],
        'required_actions': ['trigger_emergency_lock', 'preview_emergency_close', 'recovery_checklist', 'recovery_unlock'],
        'required_safety_texts': ['real order göndermez', 'owner-only', 'bot otomatik başlamaz', 'pilot durur'],
    }


def build_revision_23_quality_report(data: dict, settings: dict) -> dict:
    sections = {
        'emergency_recovery': build_emergency_recovery_quality(data, settings),
        'emergency_close': build_emergency_close_quality(data, settings),
        'disaster_recovery': build_disaster_recovery_quality(data, settings),
        'audit_timeline': build_emergency_audit_timeline_quality(data, settings),
        'ui_contract': build_emergency_ui_contract(data, settings),
    }
    blockers = []
    reviews = []
    for key, section in sections.items():
        if section.get('status') == 'blocked':
            blockers.append(key)
        elif section.get('status') == 'review':
            reviews.append(key)
    return {
        'revision': 23,
        'status': 'blocked' if blockers else ('review' if reviews else 'ok'),
        'blockers': blockers,
        'reviews': reviews,
        **sections,
    }
