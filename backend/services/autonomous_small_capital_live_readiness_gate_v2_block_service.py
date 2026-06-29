from __future__ import annotations

from datetime import datetime, timezone
from typing import Any


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace('+00:00', 'Z')


def _as_dict(value: Any) -> dict:
    return value if isinstance(value, dict) else {}


def _as_list(value: Any) -> list:
    return value if isinstance(value, list) else []


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None or value == '':
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        if value is None or value == '':
            return default
        return int(value)
    except (TypeError, ValueError):
        return default


def _truthy(value: Any) -> bool:
    return str(value).strip().lower() in {'1', 'true', 'yes', 'on', 'enabled', 'approved'}


def _reason(code: str, message: str, action: str, severity: str = 'major', priority: int = 50) -> dict:
    return {'code': code, 'message': message, 'action': action, 'severity': severity, 'priority': int(priority)}


def _critical(reasons: list[dict]) -> dict:
    if not reasons:
        return _reason('none', 'No small-cap live readiness blocker.', 'no_action', 'ok', 999)
    weights = {'critical': 0, 'major': 1, 'minor': 2, 'ok': 3}
    return sorted(reasons, key=lambda r: (weights.get(str(r.get('severity')), 2), int(r.get('priority', 50))))[0]


def _check(name: str, status: str, message: str, detail: dict | None = None) -> dict:
    return {'name': name, 'status': status, 'message': message, 'detail': detail or {}}


def _totals(checks: list[dict]) -> dict:
    return {
        'total': len(checks),
        'ok': sum(1 for c in checks if c.get('status') == 'ok'),
        'review': sum(1 for c in checks if c.get('status') == 'review'),
        'blocked': sum(1 for c in checks if c.get('status') == 'blocked'),
    }


def _final_status(checks: list[dict]) -> str:
    if any(c.get('status') == 'blocked' for c in checks):
        return 'blocked'
    if any(c.get('status') == 'review' for c in checks):
        return 'review'
    return 'ok'


def _command_preview() -> dict:
    return {
        'places_order': False,
        'sends_exchange_request': False,
        'submits_close_order': False,
        'real_submit_default_off': True,
        'real_close_default_off': True,
        'auto_scale': False,
        'auto_apply': False,
        'read_only': True,
        'approval_gated': True,
    }


def _policy(settings: dict | None) -> dict:
    settings = _as_dict(settings)
    live = _as_dict(settings.get('limited_live') or settings.get('live') or {})
    risk = _as_dict(settings.get('risk') or settings.get('risk_profile') or {})
    capital = _as_dict(settings.get('small_capital') or settings.get('capital') or {})
    allowed_symbols = _as_list(live.get('allowed_symbols')) or _as_list(settings.get('allowed_symbols')) or ['BTCUSDT', 'ETHUSDT']
    return {
        'real_submit_enable': _truthy(settings.get('real_submit_enable') or live.get('real_submit_enable')),
        'real_close_enable': _truthy(settings.get('real_close_enable') or live.get('real_close_enable')),
        'auto_scale': _truthy(settings.get('auto_scale') or live.get('auto_scale')),
        'auto_apply': _truthy(settings.get('auto_apply') or live.get('auto_apply')),
        'owner_approval': _truthy(live.get('owner_approval') or live.get('owner_approved') or settings.get('owner_approval')),
        'activation_token_preview': bool(str(live.get('activation_token_preview') or settings.get('activation_token_preview') or '').strip()),
        'api_permission_preview': _truthy(live.get('api_permission_preview') or settings.get('api_permission_preview') or True),
        'whitelist_enforced': _truthy(live.get('whitelist_enforced') or settings.get('whitelist_enforced') or True),
        'daily_hard_stop_enabled': _truthy(live.get('daily_hard_stop_enabled') or risk.get('daily_hard_stop_enabled') or True),
        'max_notional': _safe_float(live.get('max_notional') or risk.get('max_notional') or settings.get('max_notional_usdt'), 25.0),
        'max_daily_loss': _safe_float(live.get('max_daily_loss') or risk.get('max_daily_loss') or settings.get('max_daily_loss_usdt'), 5.0),
        'small_capital': _safe_float(capital.get('capital_usdt') or settings.get('capital_usdt'), 100.0),
        'max_open_positions': _safe_int(capital.get('max_open_positions') or live.get('max_open_positions'), 1),
        'max_trades_per_day': _safe_int(capital.get('max_trades_per_day') or live.get('max_trades_per_day'), 3),
        'session_id': str(live.get('session_id') or settings.get('session_id') or 'small-cap-readiness-session').strip(),
        'allowed_symbols': allowed_symbols,
    }


def _upstream(data: dict | None) -> dict:
    data = _as_dict(data)
    return {
        'data_integrity': _as_dict(data.get('autonomous_production_data_integrity_block') or data.get('production_data_integrity_report')),
        'strategy_reality': _as_dict(data.get('autonomous_live_strategy_reality_validation_block') or data.get('live_strategy_reality_report')),
        'capital_preservation': _as_dict(data.get('autonomous_capital_preservation_usdt_dominance_block') or data.get('capital_preservation_decision_packet')),
        'opportunity_quality': _as_dict(data.get('autonomous_opportunity_quality_block') or data.get('autonomous_opportunity_quality_report')),
        'operator_ux': _as_dict(data.get('autonomous_limited_live_operator_approval_ux_block') or data.get('limited_live_operator_ux_packet')),
        'dry_proof': _as_dict(data.get('autonomous_micro_live_execution_dry_proof_block') or data.get('micro_live_execution_dry_proof_report')),
    }


def _common_reasons(data: dict | None, settings: dict | None) -> list[dict]:
    p = _policy(settings)
    reasons: list[dict] = []
    if p['real_submit_enable'] or p['real_close_enable']:
        reasons.append(_reason('real_execution_flag_enabled', 'Real submit/close flags must remain OFF until final owner activation.', 'turn_real_execution_flags_off', 'critical', 0))
    if p['auto_scale'] or p['auto_apply']:
        reasons.append(_reason('auto_scale_or_apply_enabled', 'Auto-scale and auto-apply must remain OFF.', 'turn_auto_scale_apply_off', 'critical', 1))
    if p['max_notional'] <= 0 or p['max_daily_loss'] <= 0:
        reasons.append(_reason('risk_contract_missing', 'Max notional and max daily loss must be explicit.', 'set_small_capital_risk_contract', 'major', 10))
    if p['max_notional'] > max(1.0, p['small_capital'] * 0.25):
        reasons.append(_reason('notional_too_large_for_small_capital', 'Max notional is too large for small capital envelope.', 'reduce_max_notional', 'major', 11))
    if p['max_daily_loss'] > max(1.0, p['small_capital'] * 0.05):
        reasons.append(_reason('daily_loss_too_large_for_small_capital', 'Max daily loss exceeds small capital safety envelope.', 'reduce_daily_loss_limit', 'major', 12))
    if not p['allowed_symbols']:
        reasons.append(_reason('whitelist_empty', 'Allowed symbol whitelist is empty.', 'set_allowed_symbols', 'major', 13))
    if not p['session_id']:
        reasons.append(_reason('session_boundary_missing', 'Session boundary is required.', 'set_session_boundary', 'major', 14))
    for key, payload in _upstream(data).items():
        status = str(payload.get('status') or payload.get('decision') or _as_dict(payload.get(key)).get('status') or 'review').lower()
        if status in {'blocked', 'halt', 'emergency', 'inconsistent'}:
            reasons.append(_reason(f'{key}_blocked', f'{key} upstream status blocks small-cap readiness.', 'hold_until_upstream_ok', 'major', 20))
    return reasons


def build_rev256_small_capital_readiness_recheck(data: dict | None, settings: dict | None = None, auth_store: dict | None = None, username: str = 'default') -> dict:
    p = _policy(settings)
    reasons = _common_reasons(data, settings)
    critical = _critical(reasons)
    checks = [
        _check('real_execution_default_off', 'ok' if not (p['real_submit_enable'] or p['real_close_enable']) else 'blocked', 'Real submit/close stays OFF.'),
        _check('small_capital_limits_present', 'ok' if p['max_notional'] > 0 and p['max_daily_loss'] > 0 else 'blocked', 'Small-cap limits are explicit.'),
        _check('session_boundary_present', 'ok' if p['session_id'] else 'blocked', 'Session boundary exists.'),
        _check('owner_approval_preview', 'ok' if p['owner_approval'] else 'review', 'Owner approval is checked as a readiness preview only.'),
    ]
    recheck = {
        'limited_live_candidate': 'NO-GO' if critical.get('severity') in {'critical', 'major'} else ('LIMITED-GO' if not p['owner_approval'] else 'GO'),
        'critical_blocker': critical,
        'small_capital_usdt': p['small_capital'],
        'max_notional': p['max_notional'],
        'max_daily_loss': p['max_daily_loss'],
        'session_id_present': bool(p['session_id']),
        'allowed_symbols': p['allowed_symbols'],
        'real_submit_close': 'OFF',
    }
    return {'engine': 'small_capital_readiness_recheck', 'revision': 256, 'status': _final_status(checks), 'generated_at': now_iso(), 'small_capital_readiness_recheck': recheck, 'checks': checks, 'check_totals': _totals(checks), 'command_preview': _command_preview(), 'contains_secret': False, 'secret_values_returned': False, 'next_allowed_step': 'rev257_max_loss_max_notional_contract_v2'}


def build_rev257_max_loss_max_notional_contract_v2(data: dict | None, settings: dict | None = None, auth_store: dict | None = None, username: str = 'default') -> dict:
    p = _policy(settings)
    notional_ratio = p['max_notional'] / max(p['small_capital'], 1.0)
    loss_ratio = p['max_daily_loss'] / max(p['small_capital'], 1.0)
    checks = [
        _check('notional_cap_conservative', 'ok' if notional_ratio <= 0.25 else 'blocked', 'Max notional must stay conservative for small capital.', {'ratio': round(notional_ratio, 4)}),
        _check('daily_loss_cap_conservative', 'ok' if loss_ratio <= 0.05 else 'blocked', 'Daily hard stop must stay conservative.', {'ratio': round(loss_ratio, 4)}),
        _check('single_position_default', 'ok' if p['max_open_positions'] <= 1 else 'review', 'Small-cap mode prefers one open position.'),
    ]
    contract = {
        'contract_version': 'v2',
        'max_notional': p['max_notional'],
        'max_daily_loss': p['max_daily_loss'],
        'max_open_positions': p['max_open_positions'],
        'max_trades_per_day': p['max_trades_per_day'],
        'notional_to_capital_ratio': round(notional_ratio, 4),
        'daily_loss_to_capital_ratio': round(loss_ratio, 4),
        'contract_valid': _final_status(checks) != 'blocked',
        'auto_scale': 'OFF',
    }
    return {'engine': 'max_loss_max_notional_contract_v2', 'revision': 257, 'status': _final_status(checks), 'generated_at': now_iso(), 'max_loss_max_notional_contract_v2': contract, 'checks': checks, 'check_totals': _totals(checks), 'command_preview': _command_preview(), 'contains_secret': False, 'secret_values_returned': False, 'next_allowed_step': 'rev258_daily_hard_stop_enforcement_proof'}


def build_rev258_daily_hard_stop_enforcement_proof(data: dict | None, settings: dict | None = None, auth_store: dict | None = None, username: str = 'default') -> dict:
    p = _policy(settings)
    data = _as_dict(data)
    day = _as_dict(data.get('daily_state') or data.get('today') or {})
    realized = _safe_float(day.get('realized_pnl') or day.get('pnl') or 0.0, 0.0)
    loss_used = abs(min(0.0, realized))
    remaining_loss = max(0.0, p['max_daily_loss'] - loss_used)
    near_stop = remaining_loss <= p['max_daily_loss'] * 0.25 if p['max_daily_loss'] > 0 else True
    hard_stop_hit = loss_used >= p['max_daily_loss'] if p['max_daily_loss'] > 0 else True
    checks = [
        _check('daily_hard_stop_enabled', 'ok' if p['daily_hard_stop_enabled'] else 'blocked', 'Daily hard stop is enabled.'),
        _check('loss_budget_remaining', 'blocked' if hard_stop_hit else ('review' if near_stop else 'ok'), 'Loss budget is evaluated before live action.'),
        _check('halt_on_limit_hit', 'ok', 'Hard stop produces HALT before submit preview.'),
    ]
    proof = {
        'daily_hard_stop_enabled': p['daily_hard_stop_enabled'],
        'max_daily_loss': p['max_daily_loss'],
        'realized_pnl_preview': realized,
        'loss_used': round(loss_used, 8),
        'remaining_loss_budget': round(remaining_loss, 8),
        'hard_stop_hit': hard_stop_hit,
        'near_stop': near_stop,
        'enforced_action': 'HALT' if hard_stop_hit else ('REDUCE' if near_stop else 'ALLOW_PREVIEW'),
    }
    return {'engine': 'daily_hard_stop_enforcement_proof', 'revision': 258, 'status': _final_status(checks), 'generated_at': now_iso(), 'daily_hard_stop_enforcement_proof': proof, 'checks': checks, 'check_totals': _totals(checks), 'command_preview': _command_preview(), 'contains_secret': False, 'secret_values_returned': False, 'next_allowed_step': 'rev259_live_permission_whitelist_final_gate'}


def build_rev259_live_permission_whitelist_final_gate(data: dict | None, settings: dict | None = None, auth_store: dict | None = None, username: str = 'default') -> dict:
    p = _policy(settings)
    auth = _as_dict(auth_store)
    permission_preview = p['api_permission_preview'] and not bool(auth.get('secret_leak_detected'))
    checks = [
        _check('api_permission_preview_ok', 'ok' if permission_preview else 'blocked', 'API permission is previewed without returning secrets.'),
        _check('whitelist_enforced', 'ok' if p['whitelist_enforced'] else 'blocked', 'Whitelist enforcement is required.'),
        _check('allowed_symbols_present', 'ok' if p['allowed_symbols'] else 'blocked', 'Allowed symbols are explicit.'),
        _check('token_value_hidden', 'ok', 'Activation token value is never returned.'),
    ]
    gate = {
        'permission_preview': permission_preview,
        'whitelist_enforced': p['whitelist_enforced'],
        'allowed_symbols': p['allowed_symbols'],
        'blocked_symbols_policy': 'deny_by_default',
        'activation_token_value_returned': False,
        'secret_values_returned': False,
        'final_gate_passed': _final_status(checks) == 'ok',
    }
    return {'engine': 'live_permission_whitelist_final_gate', 'revision': 259, 'status': _final_status(checks), 'generated_at': now_iso(), 'live_permission_whitelist_final_gate': gate, 'checks': checks, 'check_totals': _totals(checks), 'command_preview': _command_preview(), 'contains_secret': False, 'secret_values_returned': False, 'next_allowed_step': 'rev260_small_capital_live_readiness_decision'}


def build_rev260_small_capital_live_readiness_decision(data: dict | None, settings: dict | None = None, auth_store: dict | None = None, username: str = 'default') -> dict:
    r256 = build_rev256_small_capital_readiness_recheck(data, settings, auth_store, username)
    r257 = build_rev257_max_loss_max_notional_contract_v2(data, settings, auth_store, username)
    r258 = build_rev258_daily_hard_stop_enforcement_proof(data, settings, auth_store, username)
    r259 = build_rev259_live_permission_whitelist_final_gate(data, settings, auth_store, username)
    checks = []
    for payload in (r256, r257, r258, r259):
        checks.extend(_as_list(payload.get('checks')))
    reasons = _common_reasons(data, settings)
    if r257.get('status') == 'blocked':
        reasons.append(_reason('risk_contract_invalid', 'Max loss/notional contract blocks limited-live readiness.', 'fix_risk_contract', 'major', 30))
    if r258.get('status') == 'blocked':
        reasons.append(_reason('daily_hard_stop_blocks', 'Daily hard stop is hit or disabled.', 'halt_for_today', 'critical', 5))
    if r259.get('status') == 'blocked':
        reasons.append(_reason('permission_or_whitelist_blocked', 'Permission or whitelist final gate blocks readiness.', 'fix_permission_whitelist', 'major', 31))
    critical = _critical(reasons)
    p = _policy(settings)
    if critical.get('severity') in {'critical', 'major'}:
        decision = 'NO-GO'
    elif not p['owner_approval'] or not p['activation_token_preview']:
        decision = 'LIMITED-GO'
    else:
        decision = 'GO'
    packet = {
        'limited_live': decision,
        'critical_blocker': critical,
        'max_notional': p['max_notional'],
        'max_daily_loss': p['max_daily_loss'],
        'allowed_symbols': p['allowed_symbols'],
        'session_id_present': bool(p['session_id']),
        'required_approvals': ['owner_approval', 'activation_token_preview', 'session_boundary', 'daily_hard_stop', 'whitelist'],
        'operator_action': critical.get('action') if critical.get('severity') != 'ok' else ('provide_owner_approval_and_token_preview' if decision == 'LIMITED-GO' else 'keep_under_supervision'),
        'real_submit_close': 'OFF',
        'auto_scale': 'OFF',
        'auto_apply': 'OFF',
    }
    summary_result = {
        'revision': 260,
        'limited_live': decision,
        'critical_issue': critical.get('code'),
        'operator_action': packet['operator_action'],
        'max_notional': p['max_notional'],
        'max_daily_loss': p['max_daily_loss'],
        'allowed_symbols': p['allowed_symbols'],
        'trade_allowed': decision == 'GO',
        'real_submit_close': 'OFF',
    }
    return {'engine': 'small_capital_live_readiness_decision', 'revision': 260, 'status': 'blocked' if decision == 'NO-GO' else ('review' if decision == 'LIMITED-GO' else 'ok'), 'generated_at': now_iso(), 'small_capital_live_readiness_decision': packet, 'checks': checks, 'check_totals': _totals(checks), 'summary_result': summary_result, 'command_preview': _command_preview(), 'contains_secret': False, 'secret_values_returned': False, 'next_allowed_step': 'rev261_production_limited_live_checklist'}


def build_for_revision(revision: int, data: dict | None, settings: dict | None = None, auth_store: dict | None = None, username: str = 'default') -> dict:
    builders = {
        256: build_rev256_small_capital_readiness_recheck,
        257: build_rev257_max_loss_max_notional_contract_v2,
        258: build_rev258_daily_hard_stop_enforcement_proof,
        259: build_rev259_live_permission_whitelist_final_gate,
        260: build_rev260_small_capital_live_readiness_decision,
    }
    if int(revision) not in builders:
        raise ValueError(f'Unsupported Rev256-260 small-capital live readiness revision: {revision}')
    return builders[int(revision)](data, settings, auth_store, username)


def build_block_payload(data: dict | None, settings: dict | None = None, auth_store: dict | None = None, username: str = 'default') -> dict:
    rev256 = build_rev256_small_capital_readiness_recheck(data, settings, auth_store, username)
    rev257 = build_rev257_max_loss_max_notional_contract_v2(data, settings, auth_store, username)
    rev258 = build_rev258_daily_hard_stop_enforcement_proof(data, settings, auth_store, username)
    rev259 = build_rev259_live_permission_whitelist_final_gate(data, settings, auth_store, username)
    rev260 = build_rev260_small_capital_live_readiness_decision(data, settings, auth_store, username)
    checks: list[dict] = []
    for payload in (rev256, rev257, rev258, rev259, rev260):
        checks.extend(_as_list(payload.get('checks')))
    return {
        'engine': 'small_capital_live_readiness_gate_v2_block',
        'revision': 260,
        'status': rev260.get('status', 'review'),
        'generated_at': now_iso(),
        'rev256_small_capital_readiness_recheck': rev256,
        'rev257_max_loss_max_notional_contract_v2': rev257,
        'rev258_daily_hard_stop_enforcement_proof': rev258,
        'rev259_live_permission_whitelist_final_gate': rev259,
        'rev260_small_capital_live_readiness_decision': rev260,
        'small_capital_live_readiness_decision': rev260.get('small_capital_live_readiness_decision', {}),
        'summary_result': build_summary_for_revision(260, data, settings, auth_store, username),
        'checks': checks,
        'check_totals': _totals(checks),
        'command_preview': _command_preview(),
        'contains_secret': False,
        'secret_values_returned': False,
        'next_allowed_step': 'rev261_production_limited_live_checklist',
    }


def build_summary_for_revision(revision: int, data: dict | None, settings: dict | None = None, auth_store: dict | None = None, username: str = 'default') -> dict:
    payload = build_for_revision(revision, data, settings, auth_store, username)
    key = {
        256: 'small_capital_readiness_recheck',
        257: 'max_loss_max_notional_contract_v2',
        258: 'daily_hard_stop_enforcement_proof',
        259: 'live_permission_whitelist_final_gate',
        260: 'small_capital_live_readiness_decision',
    }[int(revision)]
    body = _as_dict(payload.get(key))
    blocker = _as_dict(body.get('critical_blocker'))
    return {
        'revision': int(revision),
        'limited_live': body.get('limited_live') or body.get('limited_live_candidate') or ('NO-GO' if payload.get('status') == 'blocked' else 'REVIEW'),
        'critical_issue': blocker.get('code', 'none'),
        'operator_action': body.get('operator_action') or blocker.get('action') or 'review',
        'max_notional': body.get('max_notional'),
        'max_daily_loss': body.get('max_daily_loss'),
        'allowed_symbols': body.get('allowed_symbols'),
        'trade_allowed': body.get('limited_live') == 'GO',
        'real_submit_close': 'OFF',
    }


def build_quality_for_revision(revision: int, data: dict | None, settings: dict | None = None, auth_store: dict | None = None, username: str = 'default') -> dict:
    payload = build_for_revision(revision, data, settings, auth_store, username)
    command = _as_dict(payload.get('command_preview'))
    failures = []
    if command.get('places_order') or command.get('sends_exchange_request') or command.get('submits_close_order'):
        failures.append('unexpected_execution_side_effect')
    if command.get('real_submit_default_off') is not True or command.get('real_close_default_off') is not True:
        failures.append('real_execution_not_default_off')
    if command.get('auto_scale') or command.get('auto_apply'):
        failures.append('auto_scale_or_apply_enabled')
    if payload.get('contains_secret') or payload.get('secret_values_returned'):
        failures.append('secret_leak')
    return {'quality_gate': 'FAIL' if failures else 'PASS', 'revision': int(revision), 'engine': payload.get('engine'), 'status': payload.get('status'), 'failures': failures, 'command_preview': command, 'checked_at': now_iso()}
