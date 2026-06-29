from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
from hashlib import sha256
from typing import Any, Callable

from services.autonomous_first_micro_real_submit_enable_flag_service import build_autonomous_first_micro_real_submit_enable_flag
from services.binance_service import BinanceService, map_binance_error


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace('+00:00', 'Z')


def _safe_bool(value: Any, fallback: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        text = value.strip().lower()
        if text in {'1', 'true', 'yes', 'on', 'enabled', 'allow', 'allowed', 'ready', 'armed'}:
            return True
        if text in {'0', 'false', 'no', 'off', 'disabled', 'deny', 'blocked', 'none'}:
            return False
    if value is None:
        return fallback
    return bool(value)


def _safe_float(value: Any, fallback: float = 0.0) -> float:
    try:
        if value is None or value == '':
            return fallback
        return float(value)
    except (TypeError, ValueError):
        return fallback


def _safe_text(value: Any, fallback: str = '') -> str:
    text = str(value or '').strip()
    return text or fallback


def _policy(settings: dict | None) -> dict:
    settings = settings if isinstance(settings, dict) else {}
    raw = settings.get('autonomous_real_binance_micro_order_submitter') if isinstance(settings.get('autonomous_real_binance_micro_order_submitter'), dict) else {}
    return {
        'enabled': _safe_bool(raw.get('enabled'), True),
        'required_source_revision': 105,
        'exchange': 'binance',
        'order_endpoint': '/api/v3/order',
        'allowed_order_type': 'MARKET',
        'allowed_sides': {'BUY', 'SELL'},
        'max_micro_submit_notional_usdt': max(1.0, min(_safe_float(raw.get('max_micro_submit_notional_usdt'), 10.0), 25.0)),
        'require_source_armed_preview': _safe_bool(raw.get('require_source_armed_preview'), True),
        'require_trade_permission': _safe_bool(raw.get('require_trade_permission'), True),
        'require_owner_confirmation': _safe_bool(raw.get('require_owner_confirmation'), True),
        'require_idempotency_lock': _safe_bool(raw.get('require_idempotency_lock'), True),
        'require_audit_event': _safe_bool(raw.get('require_audit_event'), True),
        'allow_network_calls': _safe_bool(raw.get('allow_network_calls'), False),
        'allow_real_submit': _safe_bool(raw.get('allow_real_submit'), False),
        'allow_runtime_write': _safe_bool(raw.get('allow_runtime_write'), False),
        'allow_direct_orders': _safe_bool(raw.get('allow_direct_orders'), False),
        'dry_run': _safe_bool(raw.get('dry_run'), True),
        'test_order_only': _safe_bool(raw.get('test_order_only'), True),
    }


def _source(data: dict, settings: dict, auth_store: dict, username: str) -> dict:
    raw = data.get('autonomous_first_micro_real_submit_enable_flag') if isinstance(data.get('autonomous_first_micro_real_submit_enable_flag'), dict) else None
    if raw and raw.get('revision') == 105 and raw.get('engine') == 'autonomous_first_micro_real_submit_enable_flag':
        return raw
    return build_autonomous_first_micro_real_submit_enable_flag(data, settings, auth_store, username)


def _user(auth_store: dict, username: str) -> dict:
    users = auth_store.get('users') if isinstance(auth_store.get('users'), dict) else {}
    return users.get(username) if isinstance(users.get(username), dict) else {}


def _check(name: str, status: str, detail: str, required: bool = True) -> dict:
    return {'name': name, 'status': status, 'required': required, 'detail': detail}


def _build_client_order_id(username: str, source: dict, candidate: dict) -> str:
    flag = source.get('submit_enable_flag') if isinstance(source.get('submit_enable_flag'), dict) else {}
    seed = ':'.join([
        'rev106-real-binance-micro-order',
        username,
        _safe_text(flag.get('flag_id_preview')),
        _safe_text(candidate.get('symbol')),
        str(candidate.get('notional_preview_usdt')),
    ])
    return 'hmtstc_mr_' + sha256(seed.encode('utf-8')).hexdigest()[:24]


def _prepare_order_request(source: dict, policy: dict, username: str) -> dict:
    candidate = source.get('first_submit_candidate') if isinstance(source.get('first_submit_candidate'), dict) else {}
    symbol = _safe_text(candidate.get('symbol'), 'UNKNOWN').upper().replace('/', '')
    notional = _safe_float(candidate.get('notional_preview_usdt'), 0.0)
    side = _safe_text(candidate.get('side') or 'BUY', 'BUY').upper()
    client_order_id = _build_client_order_id(username, source, candidate)
    return {
        'exchange': 'binance',
        'endpoint': '/api/v3/order/test' if policy['test_order_only'] or policy['dry_run'] else policy['order_endpoint'],
        'method': 'POST',
        'symbol': symbol,
        'side': side,
        'type': policy['allowed_order_type'],
        'quoteOrderQty': round(notional, 8),
        'newClientOrderId': client_order_id,
        'test_order_only': policy['test_order_only'],
        'dry_run': policy['dry_run'],
        'contains_secret': False,
        'secret_values_returned': False,
    }


def _sanitize_response(response: dict | None) -> dict:
    response = response if isinstance(response, dict) else {}
    data = response.get('data') if isinstance(response.get('data'), dict) else {}
    safe_data = {k: data.get(k) for k in ['symbol', 'orderId', 'clientOrderId', 'transactTime', 'status', 'type', 'side', 'fills'] if k in data}
    return {
        'ok': _safe_bool(response.get('ok'), False),
        'status_code': response.get('status_code'),
        'latency_ms': response.get('latency_ms'),
        'mapped_error': response.get('mapped_error') if isinstance(response.get('mapped_error'), dict) else (map_binance_error(response.get('error')) if response.get('error') else None),
        'data': safe_data,
        'contains_secret': False,
        'secret_values_returned': False,
    }


def _submit_with_adapter(order_request: dict, submit_adapter: Callable[[dict], dict] | None, policy: dict) -> dict:
    if not policy['allow_network_calls'] or not policy['allow_real_submit'] or policy['dry_run']:
        return {
            'ok': False,
            'status_code': None,
            'adapter_state': 'NETWORK_NOT_CALLED_DRY_RUN_GUARD',
            'error': 'network_calls_or_real_submit_disabled',
            'mapped_error': map_binance_error({'code': 'LOCAL_DRY_RUN', 'msg': 'network call blocked by Rev106 policy'}),
            'latency_ms': 0.0,
        }
    if submit_adapter is not None:
        return submit_adapter(order_request)
    if policy['test_order_only']:
        service = BinanceService()
        return service.test_market_buy_order(order_request['symbol'], order_request['quoteOrderQty']) if order_request['side'] == 'BUY' else {
            'ok': False,
            'status_code': None,
            'error': 'test_market_sell_order_not_supported_by_safe_adapter',
            'mapped_error': map_binance_error({'code': 'LOCAL_GUARD', 'msg': 'sell test order requires explicit adapter'}),
            'latency_ms': 0.0,
        }
    service = BinanceService()
    return service.place_market_order(order_request['symbol'], order_request['side'], order_request['quoteOrderQty'], new_client_order_id=order_request['newClientOrderId'])


def build_autonomous_real_binance_micro_order_submitter(
    data: dict | None,
    settings: dict | None = None,
    auth_store: dict | None = None,
    username: str = 'default',
    submit_adapter: Callable[[dict], dict] | None = None,
) -> dict:
    """Rev106 real Binance micro order submitter gate.

    This layer prepares the first real Binance micro order submitter contract and
    can invoke an injected/test adapter only when explicit Rev106 live flags are
    all enabled. Default behavior is still dry-run/no-network/no-runtime-write.
    """
    data = deepcopy(data or {})
    settings = deepcopy(settings or {})
    auth_store = deepcopy(auth_store or {})
    policy = _policy(settings)
    source = _source(data, settings, auth_store, username)
    source_flag = source.get('submit_enable_flag') if isinstance(source.get('submit_enable_flag'), dict) else {}
    source_candidate = source.get('first_submit_candidate') if isinstance(source.get('first_submit_candidate'), dict) else {}
    source_api = source.get('api_permission_context') if isinstance(source.get('api_permission_context'), dict) else {}
    user = _user(auth_store, username)
    order_request = _prepare_order_request(source, policy, username)
    notional = _safe_float(order_request.get('quoteOrderQty'), 0.0)
    symbol = _safe_text(order_request.get('symbol'), 'UNKNOWN')
    side = _safe_text(order_request.get('side'), 'BUY')
    trade_permission = _safe_bool(user.get('trade_permission'), _safe_bool(source_api.get('trade_permission'), False))
    api_ready = _safe_bool(user.get('api_key_present'), _safe_bool(source_api.get('api_key_present'), False)) and _safe_bool(user.get('secret_present'), _safe_bool(source_api.get('secret_present'), False))
    idempotency_key = _safe_text(source_flag.get('source_submit_idempotency_key_preview') or source_flag.get('runtime_lock_key_preview'))
    audit_event_id = _safe_text(source_flag.get('audit_event_id'))

    checks = [
        _check('rev106_policy_enabled', 'ok' if policy['enabled'] else 'blocked', 'Rev106 submitter policy must be enabled.'),
        _check('source_revision_105', 'ok' if source.get('revision') == policy['required_source_revision'] else 'blocked', 'Rev106 must be fed by Rev105 first-submit enable flag.'),
        _check('source_not_blocked', 'ok' if source.get('status') != 'blocked' else 'blocked', f"Rev105 source status: {source.get('status', 'unknown')}"),
        _check('source_armed_preview', 'ok' if (not policy['require_source_armed_preview'] or source_flag.get('armed_preview') is True) else 'blocked', 'Rev105 flag must be armed by owner confirmation.'),
        _check('owner_confirmation_present', 'ok' if (not policy['require_owner_confirmation'] or source_flag.get('owner_confirmed') is True) else 'blocked', 'Owner confirmation is required.'),
        _check('api_key_and_secret_metadata_present', 'ok' if api_ready else 'blocked', 'API key and secret metadata must be present; values are never returned.'),
        _check('api_trade_permission_present', 'ok' if (not policy['require_trade_permission'] or trade_permission) else 'blocked', 'Trade permission is required for real micro submit.'),
        _check('symbol_usdt_spot', 'ok' if symbol.endswith('USDT') and symbol != 'UNKNOWN' else 'blocked', 'Only USDT spot symbols are allowed for first micro submit.'),
        _check('side_allowed', 'ok' if side in policy['allowed_sides'] else 'blocked', 'Side must be BUY or SELL.'),
        _check('notional_positive', 'ok' if notional > 0 else 'blocked', 'Micro order notional must be positive.'),
        _check('notional_within_micro_cap', 'ok' if 0 < notional <= policy['max_micro_submit_notional_usdt'] else 'blocked', 'Micro order notional exceeds Rev106 cap.'),
        _check('source_candidate_within_cap', 'ok' if source_candidate.get('within_cap') is True else 'blocked', 'Rev105 candidate must be within cap.'),
        _check('idempotency_key_present', 'ok' if (not policy['require_idempotency_lock'] or bool(idempotency_key)) else 'blocked', 'Runtime idempotency key is required.'),
        _check('audit_event_present', 'ok' if (not policy['require_audit_event'] or bool(audit_event_id)) else 'blocked', 'Runtime audit event preview is required.'),
        _check('runtime_write_disabled', 'ok' if not policy['allow_runtime_write'] else 'review', 'Runtime write remains disabled in Rev106.', required=False),
        _check('network_call_flag', 'ok' if policy['allow_network_calls'] else 'review', 'Network call flag is OFF; submitter will not call Binance.', required=False),
        _check('real_submit_flag', 'ok' if policy['allow_real_submit'] else 'review', 'Real submit flag is OFF by default.', required=False),
        _check('direct_order_flag', 'ok' if policy['allow_direct_orders'] else 'review', 'Direct order flag is OFF by default.', required=False),
        _check('dry_run_guard', 'ok' if not policy['dry_run'] else 'review', 'Dry-run is ON; network submit is blocked.', required=False),
    ]
    blockers = [c for c in checks if c['status'] == 'blocked' and c.get('required')]
    reviews = [c for c in checks if c['status'] == 'review']
    live_path_open = not blockers and policy['allow_network_calls'] and policy['allow_real_submit'] and policy['allow_direct_orders'] and not policy['dry_run']
    raw_response = _submit_with_adapter(order_request, submit_adapter, policy) if live_path_open else _submit_with_adapter(order_request, None, {**policy, 'allow_network_calls': False, 'allow_real_submit': False, 'dry_run': True})
    sanitized_response = _sanitize_response(raw_response)
    if live_path_open and not sanitized_response.get('ok'):
        reviews.append(_check('exchange_submit_response_review', 'review', 'Live adapter returned non-ok response.', required=False))
    status = 'blocked' if blockers else ('submitted' if live_path_open and sanitized_response.get('ok') else ('review' if reviews else 'ready'))
    readiness = {
        'blocked': 'REAL_BINANCE_MICRO_ORDER_SUBMITTER_BLOCKED',
        'review': 'REAL_BINANCE_MICRO_ORDER_SUBMITTER_REVIEW',
        'ready': 'REAL_BINANCE_MICRO_ORDER_SUBMITTER_READY_NO_NETWORK',
        'submitted': 'REAL_BINANCE_MICRO_ORDER_SUBMITTED',
    }[status]
    submitter_id = 'mros106_' + sha256(f"rev106:{username}:{order_request.get('newClientOrderId')}:{status}".encode('utf-8')).hexdigest()[:24]
    return {
        'status': status,
        'revision': 106,
        'engine': 'autonomous_real_binance_micro_order_submitter',
        'generated_at': now_iso(),
        'source_revision': source.get('revision'),
        'source_status': source.get('status'),
        'readiness': readiness,
        'submitter_id': submitter_id,
        'mode': 'real_binance_micro_order_submitter_guarded',
        'exchange': 'binance',
        'order_request_public': order_request,
        'order_response_public': sanitized_response,
        'live_path': {
            'open': live_path_open,
            'network_call_attempted': bool(live_path_open),
            'real_submit_attempted': bool(live_path_open),
            'runtime_write_attempted': False,
            'test_order_only': policy['test_order_only'],
            'dry_run': policy['dry_run'],
        },
        'guards': {
            'owner_confirmation': source_flag.get('owner_confirmed') is True,
            'source_armed_preview': source_flag.get('armed_preview') is True,
            'trade_permission': trade_permission,
            'api_ready': api_ready,
            'idempotency_key_present': bool(idempotency_key),
            'audit_event_present': bool(audit_event_id),
            'notional_within_cap': 0 < notional <= policy['max_micro_submit_notional_usdt'],
        },
        'idempotency': {
            'source_key_preview': idempotency_key,
            'client_order_id': order_request.get('newClientOrderId'),
            'duplicate_guard_required': True,
            'duplicate_detected': False,
        },
        'audit_evidence': {
            'audit_event_id': audit_event_id,
            'evidence_id': sha256(f"rev106:{username}:{submitter_id}:{audit_event_id}".encode('utf-8')).hexdigest()[:24],
            'secret_free': True,
            'runtime_write': False,
        },
        'checks': checks,
        'check_totals': {'total': len(checks), 'ok': len([c for c in checks if c['status'] == 'ok']), 'review': len(reviews), 'blocked': len(blockers)},
        'blockers': [c['name'] for c in blockers],
        'warnings': [c['name'] for c in reviews],
        'command_preview': {
            'type': 'real_binance_micro_order_submitter',
            'read_only': not live_path_open,
            'dry_run': policy['dry_run'],
            'places_order': bool(live_path_open),
            'closes_position': False,
            'sends_exchange_request': bool(live_path_open),
            'writes_runtime_state': False,
            'real_submit_enabled': bool(live_path_open),
            'next_allowed_step': 'order_status_poller_exchange_response_recorder' if status == 'submitted' else ('enable_live_flags_after_manual_go_no_go' if status != 'blocked' else 'resolve_rev106_submitter_blockers'),
        },
        'safety_contract': {
            'contains_secret': False,
            'secret_values_returned': False,
            'direct_order_placement': bool(live_path_open),
            'exchange_request': bool(live_path_open),
            'runtime_write': False,
            'approval_gated': True,
            'owner_confirmation_required': True,
            'idempotency_required': True,
            'max_micro_submit_notional_usdt': policy['max_micro_submit_notional_usdt'],
        },
        'policy_public': {k: (sorted(v) if isinstance(v, set) else v) for k, v in policy.items() if k not in {'api_key', 'api_secret'}},
        'read_only': not live_path_open,
        'dry_run': policy['dry_run'],
        'places_order': bool(live_path_open),
        'sends_exchange_request': bool(live_path_open),
        'writes_runtime_state': False,
    }


def _summary_from_payload(payload: dict) -> dict:
    command = payload.get('command_preview') if isinstance(payload.get('command_preview'), dict) else {}
    request = payload.get('order_request_public') if isinstance(payload.get('order_request_public'), dict) else {}
    live_path = payload.get('live_path') if isinstance(payload.get('live_path'), dict) else {}
    return {
        'status': payload.get('status', 'review'),
        'revision': 106,
        'engine': 'autonomous_real_binance_micro_order_submitter_summary',
        'generated_at': payload.get('generated_at'),
        'readiness': payload.get('readiness'),
        'source_revision': payload.get('source_revision'),
        'source_status': payload.get('source_status'),
        'submitter_id': payload.get('submitter_id'),
        'symbol': request.get('symbol'),
        'side': request.get('side'),
        'notional_usdt': request.get('quoteOrderQty'),
        'network_call_attempted': live_path.get('network_call_attempted') is True,
        'real_submit_attempted': live_path.get('real_submit_attempted') is True,
        'runtime_write_attempted': False,
        'test_order_only': live_path.get('test_order_only'),
        'dry_run': live_path.get('dry_run'),
        'check_totals': payload.get('check_totals') or {},
        'blockers': payload.get('blockers') or [],
        'warnings': payload.get('warnings') or [],
        'next_allowed_step': command.get('next_allowed_step'),
        'read_only': payload.get('read_only') is True,
        'places_order': payload.get('places_order') is True,
        'exchange_request': payload.get('sends_exchange_request') is True,
        'runtime_write': False,
    }


def build_summary_autonomous_real_binance_micro_order_submitter(data: dict | None, settings: dict | None = None, auth_store: dict | None = None, username: str = 'default') -> dict:
    return _summary_from_payload(build_autonomous_real_binance_micro_order_submitter(data, settings, auth_store, username))


def _sample_source() -> dict:
    return {
        'autonomous_first_micro_real_submit_enable_flag': {
            'status': 'ok',
            'revision': 105,
            'engine': 'autonomous_first_micro_real_submit_enable_flag',
            'readiness': 'FIRST_MICRO_REAL_SUBMIT_FLAG_ARMED_PREVIEW',
            'submit_enable_flag': {
                'flag_id_preview': 'sample_flag',
                'configured': True,
                'requested': True,
                'owner_confirmed': True,
                'armed_preview': True,
                'one_shot': True,
                'single_symbol_only': True,
                'max_first_submit_notional_usdt': 10,
                'source_submit_idempotency_key_preview': 'sample_submit_key',
                'runtime_lock_key_preview': 'sample_lock',
                'audit_event_id': 'sample_audit_event',
                'writes_runtime_state': False,
            },
            'api_permission_context': {'api_key_present': True, 'secret_present': True, 'read_permission': True, 'trade_permission': True, 'secret_values_returned': False},
            'first_submit_candidate': {'symbol': 'BTCUSDT', 'side': 'BUY', 'notional_preview_usdt': 6.0, 'cap_usdt': 10.0, 'within_cap': True, 'submit_enabled_preview': True},
            'command_preview': {'places_order': False, 'sends_exchange_request': False, 'writes_runtime_state': False, 'real_submit_enabled': False},
            'safety_contract': {'contains_secret': False, 'secret_values_returned': False, 'direct_order_placement': False, 'exchange_request': False, 'runtime_write': False},
        }
    }


def _sample_auth(username: str) -> dict:
    return {'users': {username: {'role': 'owner', 'api_key_present': True, 'secret_present': True, 'read_permission': True, 'trade_permission': True}}}


def build_autonomous_real_binance_micro_order_submitter_quality(data: dict | None = None, settings: dict | None = None, auth_store: dict | None = None, username: str = 'default') -> dict:
    sample_settings = settings or {'autonomous_real_binance_micro_order_submitter': {'enabled': True, 'max_micro_submit_notional_usdt': 10, 'allow_network_calls': False, 'allow_real_submit': False, 'allow_direct_orders': False, 'allow_runtime_write': False, 'dry_run': True, 'test_order_only': True}}
    payload = build_autonomous_real_binance_micro_order_submitter(data or _sample_source(), sample_settings, auth_store or _sample_auth(username), username)
    command = payload.get('command_preview') if isinstance(payload.get('command_preview'), dict) else {}
    safety = payload.get('safety_contract') if isinstance(payload.get('safety_contract'), dict) else {}
    live_path = payload.get('live_path') if isinstance(payload.get('live_path'), dict) else {}
    request = payload.get('order_request_public') if isinstance(payload.get('order_request_public'), dict) else {}
    checks = {
        'revision_is_106': payload.get('revision') == 106,
        'source_revision_is_105': payload.get('source_revision') == 105,
        'readiness_present': payload.get('readiness') in {'REAL_BINANCE_MICRO_ORDER_SUBMITTER_BLOCKED', 'REAL_BINANCE_MICRO_ORDER_SUBMITTER_REVIEW', 'REAL_BINANCE_MICRO_ORDER_SUBMITTER_READY_NO_NETWORK', 'REAL_BINANCE_MICRO_ORDER_SUBMITTED'},
        'public_order_request_present': request.get('endpoint') in {'/api/v3/order/test', '/api/v3/order'} and request.get('contains_secret') is False,
        'network_not_called_by_default': live_path.get('network_call_attempted') is False,
        'real_submit_not_attempted_by_default': live_path.get('real_submit_attempted') is False,
        'runtime_write_not_attempted': live_path.get('runtime_write_attempted') is False and command.get('writes_runtime_state') is False,
        'direct_order_default_off': command.get('places_order') is False,
        'exchange_request_default_off': command.get('sends_exchange_request') is False,
        'secret_free_contract': safety.get('contains_secret') is False and safety.get('secret_values_returned') is False,
        'summary_revision_is_106': _summary_from_payload(payload).get('revision') == 106,
    }
    passed = all(checks.values())
    return {
        'status': 'ok' if passed else 'review',
        'revision': 106,
        'engine': 'autonomous_real_binance_micro_order_submitter_quality',
        'generated_at': now_iso(),
        'quality_status': 'REAL_BINANCE_MICRO_ORDER_SUBMITTER_OK' if passed else 'REAL_BINANCE_MICRO_ORDER_SUBMITTER_REVIEW',
        'checks': checks,
        'summary': _summary_from_payload(payload),
        'sample_readiness': payload.get('readiness'),
        'sample_totals': payload.get('check_totals') or {},
    }
