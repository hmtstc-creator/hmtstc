from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
from hashlib import sha256
from typing import Any, Callable

from services.autonomous_real_binance_micro_order_submitter_service import build_autonomous_real_binance_micro_order_submitter
from services.binance_service import map_binance_error


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
    raw = settings.get('autonomous_order_status_poller_exchange_response_recorder') if isinstance(settings.get('autonomous_order_status_poller_exchange_response_recorder'), dict) else {}
    return {
        'enabled': _safe_bool(raw.get('enabled'), True),
        'required_source_revision': 106,
        'exchange': 'binance',
        'poll_endpoint': '/api/v3/order',
        'allowed_statuses': {'NEW', 'FILLED', 'PARTIALLY_FILLED', 'CANCELED', 'REJECTED', 'EXPIRED'},
        'require_source_submitter': _safe_bool(raw.get('require_source_submitter'), True),
        'require_public_order_request': _safe_bool(raw.get('require_public_order_request'), True),
        'require_client_order_id': _safe_bool(raw.get('require_client_order_id'), True),
        'allow_network_calls': _safe_bool(raw.get('allow_network_calls'), False),
        'allow_runtime_write': _safe_bool(raw.get('allow_runtime_write'), False),
        'record_exchange_response': _safe_bool(raw.get('record_exchange_response'), True),
        'dry_run': _safe_bool(raw.get('dry_run'), True),
    }


def _source(data: dict, settings: dict, auth_store: dict, username: str) -> dict:
    raw = data.get('autonomous_real_binance_micro_order_submitter') if isinstance(data.get('autonomous_real_binance_micro_order_submitter'), dict) else None
    if raw and raw.get('revision') == 106 and raw.get('engine') == 'autonomous_real_binance_micro_order_submitter':
        return raw
    return build_autonomous_real_binance_micro_order_submitter(data, settings, auth_store, username)


def _check(name: str, status: str, detail: str, required: bool = True) -> dict:
    return {'name': name, 'status': status, 'required': required, 'detail': detail}


def _poll_request(source: dict, policy: dict) -> dict:
    order = source.get('order_request_public') if isinstance(source.get('order_request_public'), dict) else {}
    response = source.get('order_response_public') if isinstance(source.get('order_response_public'), dict) else {}
    response_data = response.get('data') if isinstance(response.get('data'), dict) else {}
    return {
        'exchange': 'binance',
        'endpoint': policy['poll_endpoint'],
        'method': 'GET',
        'symbol': _safe_text(order.get('symbol') or response_data.get('symbol'), 'UNKNOWN').upper(),
        'orderId': response_data.get('orderId'),
        'origClientOrderId': _safe_text(response_data.get('clientOrderId') or order.get('newClientOrderId')),
        'contains_secret': False,
        'secret_values_returned': False,
    }


def _normalize_order_status(raw_response: dict | None, poll_request: dict, source: dict) -> dict:
    raw_response = raw_response if isinstance(raw_response, dict) else {}
    data = raw_response.get('data') if isinstance(raw_response.get('data'), dict) else {}
    source_response = source.get('order_response_public') if isinstance(source.get('order_response_public'), dict) else {}
    source_data = source_response.get('data') if isinstance(source_response.get('data'), dict) else {}
    status = _safe_text(data.get('status') or source_data.get('status') or ('DRY_RUN_NOT_SUBMITTED' if not source_response.get('ok') else 'NEW'), 'UNKNOWN').upper()
    executed_qty = _safe_float(data.get('executedQty') or data.get('executed_qty') or source_data.get('executedQty'), 0.0)
    cumulative_quote_qty = _safe_float(data.get('cummulativeQuoteQty') or data.get('cumulativeQuoteQty') or data.get('cummulative_quote_qty') or source_data.get('cummulativeQuoteQty'), 0.0)
    avg_price = _safe_float(data.get('avgPrice') or data.get('avg_price'), 0.0)
    if avg_price <= 0 and executed_qty > 0 and cumulative_quote_qty > 0:
        avg_price = cumulative_quote_qty / executed_qty
    return {
        'symbol': _safe_text(data.get('symbol') or poll_request.get('symbol'), 'UNKNOWN').upper(),
        'order_id': data.get('orderId') or source_data.get('orderId'),
        'client_order_id': _safe_text(data.get('clientOrderId') or poll_request.get('origClientOrderId')),
        'status': status,
        'side': _safe_text(data.get('side') or source_data.get('side') or (source.get('order_request_public') or {}).get('side')),
        'type': _safe_text(data.get('type') or source_data.get('type') or (source.get('order_request_public') or {}).get('type')),
        'executed_qty': executed_qty,
        'cumulative_quote_qty': cumulative_quote_qty,
        'avg_price': round(avg_price, 10) if avg_price else 0.0,
        'update_time': data.get('updateTime') or data.get('transactTime') or source_data.get('transactTime'),
        'fills_present': isinstance(data.get('fills') or source_data.get('fills'), list),
        'terminal': status in {'FILLED', 'CANCELED', 'REJECTED', 'EXPIRED'},
        'contains_secret': False,
        'secret_values_returned': False,
    }


def _sanitize_poll_response(response: dict | None) -> dict:
    response = response if isinstance(response, dict) else {}
    data = response.get('data') if isinstance(response.get('data'), dict) else {}
    allowed = ['symbol', 'orderId', 'clientOrderId', 'status', 'side', 'type', 'executedQty', 'cummulativeQuoteQty', 'updateTime', 'transactTime', 'fills']
    safe_data = {k: data.get(k) for k in allowed if k in data}
    return {
        'ok': _safe_bool(response.get('ok'), False),
        'status_code': response.get('status_code'),
        'latency_ms': response.get('latency_ms'),
        'mapped_error': response.get('mapped_error') if isinstance(response.get('mapped_error'), dict) else (map_binance_error(response.get('error')) if response.get('error') else None),
        'data': safe_data,
        'contains_secret': False,
        'secret_values_returned': False,
    }


def _poll_with_adapter(poll_request: dict, status_adapter: Callable[[dict], dict] | None, policy: dict) -> dict:
    if not policy['allow_network_calls'] or policy['dry_run']:
        return {
            'ok': False,
            'status_code': None,
            'adapter_state': 'NETWORK_NOT_CALLED_DRY_RUN_GUARD',
            'error': 'network_calls_disabled_or_dry_run',
            'mapped_error': map_binance_error({'code': 'LOCAL_DRY_RUN', 'msg': 'status poll blocked by Rev107 policy'}),
            'latency_ms': 0.0,
        }
    if status_adapter is not None:
        return status_adapter(poll_request)
    return {
        'ok': False,
        'status_code': None,
        'adapter_state': 'NO_LIVE_STATUS_ADAPTER',
        'error': 'no_status_adapter_configured',
        'mapped_error': map_binance_error({'code': 'LOCAL_GUARD', 'msg': 'live status polling requires explicit adapter'}),
        'latency_ms': 0.0,
    }


def _record_preview(username: str, source: dict, poll_request: dict, normalized: dict, policy: dict) -> dict:
    seed = ':'.join(['rev107-order-status-record', username, _safe_text(source.get('submitter_id')), _safe_text(normalized.get('client_order_id')), _safe_text(normalized.get('status'))])
    return {
        'record_id': 'osr107_' + sha256(seed.encode('utf-8')).hexdigest()[:24],
        'record_type': 'order_status_snapshot',
        'exchange': 'binance',
        'symbol': normalized.get('symbol'),
        'client_order_id': normalized.get('client_order_id'),
        'status': normalized.get('status'),
        'terminal': normalized.get('terminal') is True,
        'source_submitter_id': source.get('submitter_id'),
        'poll_endpoint': poll_request.get('endpoint'),
        'contains_secret': False,
        'secret_values_returned': False,
        'writes_runtime_state': bool(policy['allow_runtime_write']),
        'write_mode': 'runtime_write_disabled_preview' if not policy['allow_runtime_write'] else 'runtime_write_requires_live_store',
    }


def build_autonomous_order_status_poller_exchange_response_recorder(
    data: dict | None,
    settings: dict | None = None,
    auth_store: dict | None = None,
    username: str = 'default',
    status_adapter: Callable[[dict], dict] | None = None,
) -> dict:
    """Rev107 order status poller + exchange response recorder.

    It normalizes post-submit exchange status and produces a secret-free record
    preview. Default is no-network/no-runtime-write; an injected adapter is used
    only when explicit network flags are opened.
    """
    data = deepcopy(data or {})
    settings = deepcopy(settings or {})
    auth_store = deepcopy(auth_store or {})
    policy = _policy(settings)
    source = _source(data, settings, auth_store, username)
    order_request = source.get('order_request_public') if isinstance(source.get('order_request_public'), dict) else {}
    order_response = source.get('order_response_public') if isinstance(source.get('order_response_public'), dict) else {}
    live_path = source.get('live_path') if isinstance(source.get('live_path'), dict) else {}
    poll_request = _poll_request(source, policy)
    network_path_open = policy['allow_network_calls'] and not policy['dry_run'] and bool(poll_request.get('origClientOrderId'))
    raw_poll_response = _poll_with_adapter(poll_request, status_adapter, policy) if network_path_open else _poll_with_adapter(poll_request, None, {**policy, 'allow_network_calls': False, 'dry_run': True})
    sanitized_poll_response = _sanitize_poll_response(raw_poll_response)
    normalized_status = _normalize_order_status(sanitized_poll_response if sanitized_poll_response.get('ok') else order_response, poll_request, source)
    record = _record_preview(username, source, poll_request, normalized_status, policy)

    checks = [
        _check('rev107_policy_enabled', 'ok' if policy['enabled'] else 'blocked', 'Rev107 poller policy must be enabled.'),
        _check('source_revision_106', 'ok' if source.get('revision') == policy['required_source_revision'] else 'blocked', 'Rev107 must consume Rev106 submitter output.'),
        _check('source_submitter_present', 'ok' if (not policy['require_source_submitter'] or bool(source.get('submitter_id'))) else 'blocked', 'Rev106 submitter id is required.'),
        _check('public_order_request_present', 'ok' if (not policy['require_public_order_request'] or bool(order_request.get('symbol'))) else 'blocked', 'Public order request is required.'),
        _check('client_order_id_present', 'ok' if (not policy['require_client_order_id'] or bool(poll_request.get('origClientOrderId'))) else 'blocked', 'Client order id is required for status polling.'),
        _check('source_secret_free', 'ok' if not order_request.get('contains_secret') and not order_response.get('contains_secret') else 'blocked', 'Source payload must be secret-free.'),
        _check('source_runtime_write_disabled', 'ok' if not live_path.get('runtime_write_attempted') else 'blocked', 'Rev106 must not write runtime state.'),
        _check('poll_response_secret_free', 'ok' if not sanitized_poll_response.get('contains_secret') and not normalized_status.get('contains_secret') else 'blocked', 'Poll response must be secret-free.'),
        _check('record_secret_free', 'ok' if record.get('contains_secret') is False and record.get('secret_values_returned') is False else 'blocked', 'Recorder output must be secret-free.'),
        _check('runtime_write_disabled', 'ok' if not policy['allow_runtime_write'] else 'review', 'Runtime write stays disabled in Rev107 package.', required=False),
        _check('network_call_flag', 'ok' if policy['allow_network_calls'] else 'review', 'Status polling network flag is OFF by default.', required=False),
        _check('dry_run_guard', 'ok' if not policy['dry_run'] else 'review', 'Dry-run is ON; no Binance status request is sent.', required=False),
        _check('source_submit_status', 'ok' if source.get('status') == 'submitted' else 'review', f"Rev106 source status: {source.get('status', 'unknown')}", required=False),
        _check('normalized_status_known', 'ok' if normalized_status.get('status') in policy['allowed_statuses'] else 'review', 'Status is normalized, but source may be dry-run/not submitted.', required=False),
    ]
    blockers = [c for c in checks if c['status'] == 'blocked' and c.get('required')]
    reviews = [c for c in checks if c['status'] == 'review']
    status = 'blocked' if blockers else ('ok' if network_path_open and normalized_status.get('status') in policy['allowed_statuses'] else 'review')
    readiness = {
        'blocked': 'ORDER_STATUS_POLLER_RESPONSE_RECORDER_BLOCKED',
        'review': 'ORDER_STATUS_POLLER_RESPONSE_RECORDER_REVIEW',
        'ok': 'ORDER_STATUS_POLLER_RESPONSE_RECORDED',
    }[status]
    poller_id = 'osp107_' + sha256(f"rev107:{username}:{record.get('record_id')}:{status}".encode('utf-8')).hexdigest()[:24]
    return {
        'status': status,
        'revision': 107,
        'engine': 'autonomous_order_status_poller_exchange_response_recorder',
        'generated_at': now_iso(),
        'source_revision': source.get('revision'),
        'source_status': source.get('status'),
        'readiness': readiness,
        'poller_id': poller_id,
        'mode': 'order_status_poller_exchange_response_recorder_guarded',
        'exchange': 'binance',
        'poll_request_public': poll_request,
        'poll_response_public': sanitized_poll_response,
        'normalized_order_status': normalized_status,
        'exchange_response_record_preview': record,
        'live_path': {
            'open': bool(network_path_open),
            'network_call_attempted': bool(network_path_open),
            'runtime_write_attempted': False,
            'dry_run': policy['dry_run'],
        },
        'checks': checks,
        'check_totals': {'total': len(checks), 'ok': len([c for c in checks if c['status'] == 'ok']), 'review': len(reviews), 'blocked': len(blockers)},
        'blockers': [c['name'] for c in blockers],
        'warnings': [c['name'] for c in reviews],
        'command_preview': {
            'type': 'order_status_poller_exchange_response_recorder',
            'read_only': not network_path_open,
            'places_order': False,
            'closes_position': False,
            'sends_exchange_request': bool(network_path_open),
            'writes_runtime_state': False,
            'records_exchange_response': bool(policy['record_exchange_response']),
            'next_allowed_step': 'balance_reconciliation_manual_attention_guard' if status != 'blocked' else 'resolve_rev107_status_poller_blockers',
        },
        'safety_contract': {
            'contains_secret': False,
            'secret_values_returned': False,
            'direct_order_placement': False,
            'exchange_request': bool(network_path_open),
            'runtime_write': False,
            'approval_gated': True,
            'status_polling_gated': True,
            'response_record_secret_free': True,
        },
        'policy_public': {k: (sorted(v) if isinstance(v, set) else v) for k, v in policy.items()},
        'read_only': not network_path_open,
        'places_order': False,
        'sends_exchange_request': bool(network_path_open),
        'writes_runtime_state': False,
    }


def _summary_from_payload(payload: dict) -> dict:
    command = payload.get('command_preview') if isinstance(payload.get('command_preview'), dict) else {}
    status = payload.get('normalized_order_status') if isinstance(payload.get('normalized_order_status'), dict) else {}
    record = payload.get('exchange_response_record_preview') if isinstance(payload.get('exchange_response_record_preview'), dict) else {}
    live_path = payload.get('live_path') if isinstance(payload.get('live_path'), dict) else {}
    return {
        'status': payload.get('status', 'review'),
        'revision': 107,
        'engine': 'autonomous_order_status_poller_exchange_response_recorder_summary',
        'generated_at': payload.get('generated_at'),
        'readiness': payload.get('readiness'),
        'source_revision': payload.get('source_revision'),
        'source_status': payload.get('source_status'),
        'poller_id': payload.get('poller_id'),
        'symbol': status.get('symbol'),
        'order_status': status.get('status'),
        'terminal': status.get('terminal') is True,
        'client_order_id': status.get('client_order_id'),
        'record_id': record.get('record_id'),
        'network_call_attempted': live_path.get('network_call_attempted') is True,
        'runtime_write_attempted': False,
        'check_totals': payload.get('check_totals') or {},
        'blockers': payload.get('blockers') or [],
        'warnings': payload.get('warnings') or [],
        'next_allowed_step': command.get('next_allowed_step'),
        'read_only': payload.get('read_only') is True,
        'places_order': False,
        'exchange_request': payload.get('sends_exchange_request') is True,
        'runtime_write': False,
    }


def build_summary_autonomous_order_status_poller_exchange_response_recorder(data: dict | None, settings: dict | None = None, auth_store: dict | None = None, username: str = 'default') -> dict:
    return _summary_from_payload(build_autonomous_order_status_poller_exchange_response_recorder(data, settings, auth_store, username))


def _sample_source() -> dict:
    return {
        'autonomous_real_binance_micro_order_submitter': {
            'status': 'submitted',
            'revision': 106,
            'engine': 'autonomous_real_binance_micro_order_submitter',
            'readiness': 'REAL_BINANCE_MICRO_ORDER_SUBMITTED',
            'submitter_id': 'sample_submitter',
            'order_request_public': {'exchange': 'binance', 'endpoint': '/api/v3/order', 'method': 'POST', 'symbol': 'BTCUSDT', 'side': 'BUY', 'type': 'MARKET', 'quoteOrderQty': 6.0, 'newClientOrderId': 'sample_client_order', 'contains_secret': False, 'secret_values_returned': False},
            'order_response_public': {'ok': True, 'status_code': 200, 'latency_ms': 12, 'data': {'symbol': 'BTCUSDT', 'orderId': 123, 'clientOrderId': 'sample_client_order', 'status': 'FILLED', 'side': 'BUY', 'type': 'MARKET', 'executedQty': '0.0001', 'cummulativeQuoteQty': '6.0'}, 'contains_secret': False, 'secret_values_returned': False},
            'live_path': {'network_call_attempted': True, 'real_submit_attempted': True, 'runtime_write_attempted': False, 'dry_run': False},
            'command_preview': {'places_order': True, 'sends_exchange_request': True, 'writes_runtime_state': False},
            'safety_contract': {'contains_secret': False, 'secret_values_returned': False, 'runtime_write': False},
        }
    }


def _sample_auth(username: str) -> dict:
    return {'users': {username: {'role': 'owner', 'api_key_present': True, 'secret_present': True, 'read_permission': True, 'trade_permission': True}}}


def build_autonomous_order_status_poller_exchange_response_recorder_quality(data: dict | None = None, settings: dict | None = None, auth_store: dict | None = None, username: str = 'default') -> dict:
    sample_settings = settings or {'autonomous_order_status_poller_exchange_response_recorder': {'enabled': True, 'allow_network_calls': False, 'allow_runtime_write': False, 'dry_run': True}}
    payload = build_autonomous_order_status_poller_exchange_response_recorder(data or _sample_source(), sample_settings, auth_store or _sample_auth(username), username)
    command = payload.get('command_preview') if isinstance(payload.get('command_preview'), dict) else {}
    safety = payload.get('safety_contract') if isinstance(payload.get('safety_contract'), dict) else {}
    record = payload.get('exchange_response_record_preview') if isinstance(payload.get('exchange_response_record_preview'), dict) else {}
    live_path = payload.get('live_path') if isinstance(payload.get('live_path'), dict) else {}
    checks = {
        'revision_is_107': payload.get('revision') == 107,
        'source_revision_is_106': payload.get('source_revision') == 106,
        'normalized_status_present': bool((payload.get('normalized_order_status') or {}).get('status')),
        'record_preview_secret_free': record.get('contains_secret') is False and record.get('secret_values_returned') is False,
        'network_not_called_by_default': live_path.get('network_call_attempted') is False,
        'runtime_write_not_attempted': live_path.get('runtime_write_attempted') is False and command.get('writes_runtime_state') is False,
        'direct_order_default_off': command.get('places_order') is False,
        'secret_free_contract': safety.get('contains_secret') is False and safety.get('secret_values_returned') is False,
        'summary_revision_is_107': _summary_from_payload(payload).get('revision') == 107,
    }
    passed = all(checks.values())
    return {
        'status': 'ok' if passed else 'review',
        'revision': 107,
        'engine': 'autonomous_order_status_poller_exchange_response_recorder_quality',
        'generated_at': now_iso(),
        'quality_status': 'ORDER_STATUS_POLLER_RESPONSE_RECORDER_OK' if passed else 'ORDER_STATUS_POLLER_RESPONSE_RECORDER_REVIEW',
        'checks': checks,
        'summary': _summary_from_payload(payload),
        'sample_readiness': payload.get('readiness'),
        'sample_totals': payload.get('check_totals') or {},
    }
