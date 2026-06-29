
from __future__ import annotations

import hashlib
import json
from collections import Counter, defaultdict
from datetime import datetime, timezone, timedelta
from typing import Any

from services.audit_forensics_service import (
    audit_export_manifest,
    audit_taxonomy_report,
    audit_completeness_report,
    audit_immutability_report,
    enrich_audit_chain,
    security_trading_timeline,
)
from services.observability_service import (
    build_latency_report,
    build_endpoint_error_report,
    build_stale_report,
    build_deploy_report,
    build_observability_summary,
)

LEVEL1_REVISION = 50


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace('+00:00', 'Z')


def _safe_list(value: Any) -> list:
    return value if isinstance(value, list) else []


def _safe_dict(value: Any) -> dict:
    return value if isinstance(value, dict) else {}


def _parse_time(value: Any):
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(str(value).replace('Z', '+00:00'))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except Exception:
        return None


def _bucket_time(value: Any, minutes: int = 15) -> str:
    dt = _parse_time(value) or datetime.now(timezone.utc)
    minute = (dt.minute // minutes) * minutes
    dt = dt.replace(minute=minute, second=0, microsecond=0)
    return dt.isoformat().replace('+00:00', 'Z')


def _audit_items(data: dict) -> list[dict]:
    return [x for x in _safe_list(_safe_dict(data).get('audit')) if isinstance(x, dict)]


def _log_items(data: dict) -> list[dict]:
    return [x for x in _safe_list(_safe_dict(data).get('logs')) if isinstance(x, dict)]


def build_observability_trend(data: dict, settings: dict | None = None, window_minutes: int = 15) -> dict:
    data = _safe_dict(data)
    settings = _safe_dict(settings)
    audit = _audit_items(data)
    logs = _log_items(data)
    bot_traces = [x for x in _safe_list(data.get('bot_loop_traces')) if isinstance(x, dict)]
    health_history = [x for x in _safe_list(data.get('health_history')) if isinstance(x, dict)]
    buckets: dict[str, dict] = defaultdict(lambda: {
        'audit_events': 0,
        'errors': 0,
        'blocked': 0,
        'warnings': 0,
        'bot_loop_samples': 0,
        'bot_loop_total_ms': 0.0,
        'health_samples': 0,
        'health_total_ms': 0.0,
    })
    for item in audit:
        b = buckets[_bucket_time(item.get('time') or item.get('created_at') or item.get('timestamp'), window_minutes)]
        b['audit_events'] += 1
        result = str(item.get('result') or '').lower()
        severity = str(item.get('severity') or '').lower()
        if result in {'error', 'failed'} or severity == 'critical':
            b['errors'] += 1
        if result == 'blocked' or severity == 'blocked':
            b['blocked'] += 1
        if severity == 'warning':
            b['warnings'] += 1
    for item in logs:
        b = buckets[_bucket_time(item.get('time') or item.get('created_at') or item.get('timestamp'), window_minutes)]
        level = str(item.get('level') or '').lower()
        if level == 'error':
            b['errors'] += 1
        elif level in {'warn', 'warning'}:
            b['warnings'] += 1
    for item in bot_traces[-200:]:
        b = buckets[_bucket_time(item.get('time') or item.get('created_at') or item.get('started_at'), window_minutes)]
        try:
            ms = float(item.get('duration_ms') or float(item.get('duration_seconds') or 0) * 1000)
        except Exception:
            ms = 0.0
        if ms > 0:
            b['bot_loop_samples'] += 1
            b['bot_loop_total_ms'] += ms
    for item in health_history[-200:]:
        b = buckets[_bucket_time(item.get('time') or item.get('created_at') or item.get('timestamp'), window_minutes)]
        try:
            ms = float(item.get('duration_ms') or 0)
        except Exception:
            ms = 0.0
        if ms > 0:
            b['health_samples'] += 1
            b['health_total_ms'] += ms
    points = []
    for bucket in sorted(buckets):
        row = dict(buckets[bucket])
        row['bucket'] = bucket
        row['bot_loop_avg_ms'] = round(row['bot_loop_total_ms'] / row['bot_loop_samples'], 2) if row['bot_loop_samples'] else 0.0
        row['health_avg_ms'] = round(row['health_total_ms'] / row['health_samples'], 2) if row['health_samples'] else 0.0
        row.pop('bot_loop_total_ms', None)
        row.pop('health_total_ms', None)
        points.append(row)
    latency = build_latency_report(data)
    stale = build_stale_report(data, settings)
    status = 'ok'
    if any(p['errors'] or p['blocked'] for p in points[-8:]) or stale.get('status') == 'blocked':
        status = 'review'
    if stale.get('status') == 'blocked' and latency.get('status') == 'blocked':
        status = 'blocked'
    return {
        'status': status,
        'generated_at': now_iso(),
        'window_minutes': window_minutes,
        'points': points[-96:],
        'summary': {
            'total_points': len(points),
            'recent_errors': sum(p['errors'] for p in points[-8:]),
            'recent_blocked': sum(p['blocked'] for p in points[-8:]),
            'bot_loop_avg_ms': latency.get('bot_loop_avg_ms', 0),
            'stale_status': stale.get('status'),
        },
        'policy': {'read_only': True, 'does_not_unlock_real_trade': True},
    }


def build_observability_alerts(data: dict, settings: dict | None = None) -> dict:
    data = _safe_dict(data)
    settings = _safe_dict(settings)
    latency = build_latency_report(data)
    errors = build_endpoint_error_report(data)
    stale = build_stale_report(data, settings)
    deploy = build_deploy_report(data)
    alerts = []
    def add(severity: str, code: str, message: str, source: str, detail: dict | None = None):
        alerts.append({'severity': severity, 'code': code, 'message': message, 'source': source, 'detail': detail or {}})
    for warning in latency.get('warnings') or []:
        add('warning', str(warning), 'Latency warning observed.', 'latency', latency)
    for blocker in stale.get('blockers') or []:
        add('blocked' if stale.get('status') == 'blocked' else 'warning', str(blocker), 'Stale/runtime blocker observed.', 'stale', stale)
    if errors.get('total_errors'):
        add('warning' if errors.get('error_rate_pct', 0) < 20 else 'critical', 'endpoint_errors_observed', 'Endpoint errors detected.', 'endpoint_errors', {'total_errors': errors.get('total_errors'), 'error_rate_pct': errors.get('error_rate_pct')})
    if deploy.get('status') != 'ok':
        add('warning', 'deploy_marker_review', 'Deploy marker review required.', 'deploy', deploy.get('deploy_markers') or {})
    critical_audit = [x for x in _audit_items(data) if str(x.get('severity') or '').lower() in {'critical', 'blocked'}]
    for item in list(reversed(critical_audit[-10:])):
        add(str(item.get('severity') or 'critical'), str(item.get('action') or 'audit_critical'), str(item.get('message') or 'Critical audit item.'), 'audit', {'endpoint': item.get('endpoint'), 'result': item.get('result'), 'time': item.get('time')})
    status = 'ok'
    if any(a['severity'] in {'warning', 'critical', 'blocked'} for a in alerts):
        status = 'review'
    if any(a['severity'] in {'critical', 'blocked'} for a in alerts):
        status = 'blocked'
    return {'status': status, 'generated_at': now_iso(), 'count': len(alerts), 'alerts': alerts[:100], 'policy': {'read_only': True}}


def build_observability_final_report(data: dict, settings: dict | None = None) -> dict:
    data = _safe_dict(data)
    settings = _safe_dict(settings)
    summary = build_observability_summary(data, settings)
    trend = build_observability_trend(data, settings)
    alerts = build_observability_alerts(data, settings)
    score = int(summary.get('score') or 0)
    if trend.get('status') == 'review':
        score = max(score - 5, 0)
    if alerts.get('status') == 'blocked':
        score = max(score - 15, 0)
    status = 'ok' if score >= 80 and alerts.get('status') != 'blocked' else ('review' if score >= 60 else 'blocked')
    return {
        'status': status,
        'revision': LEVEL1_REVISION,
        'generated_at': now_iso(),
        'score': score,
        'summary': summary,
        'trend': trend,
        'alerts': alerts,
        'required_endpoints': [
            '/api/observability/summary',
            '/api/observability/trend',
            '/api/observability/alerts',
            '/api/audit/search-final',
            '/api/audit/retention',
            '/api/audit/tamper-warning',
        ],
        'policy': {'read_only': True, 'does_not_place_orders': True, 'does_not_mutate_runtime': True},
    }


def build_audit_search_final(data: dict, query: str | None = None, category: str | None = None, severity: str | None = None, result: str | None = None, limit: int = 500) -> dict:
    items = enrich_audit_chain(_audit_items(data))
    q = str(query or '').lower().strip()
    filtered = []
    for item in items:
        if category and category != 'all' and str(item.get('category') or '') != category:
            continue
        if severity and severity != 'all' and str(item.get('severity') or '') != severity:
            continue
        if result and result != 'all' and str(item.get('result') or '') != result:
            continue
        hay = ' '.join(str(item.get(k) or '').lower() for k in ['action','result','message','user','role','page','endpoint','category','severity','request_id','correlation_id','subject'])
        if q and q not in hay:
            continue
        filtered.append(item)
    return {
        'status': 'ok',
        'generated_at': now_iso(),
        'count': len(filtered),
        'items': list(reversed(filtered[-max(1, min(limit, 2000)):])),
        'filters': {'query': query, 'category': category, 'severity': severity, 'result': result, 'limit': limit},
        'taxonomy': audit_taxonomy_report(filtered),
        'completeness': audit_completeness_report(filtered),
        'export_manifest': audit_export_manifest(filtered, 'json', {'query': query, 'category': category, 'severity': severity, 'result': result}),
    }


def build_audit_retention_report(data: dict, retention_days: int = 365) -> dict:
    items = _audit_items(data)
    now = datetime.now(timezone.utc)
    old_count = 0
    dated = 0
    for item in items:
        dt = _parse_time(item.get('time') or item.get('created_at') or item.get('timestamp'))
        if dt:
            dated += 1
            if now - dt > timedelta(days=retention_days):
                old_count += 1
    return {
        'status': 'ok' if old_count == 0 else 'review',
        'generated_at': now_iso(),
        'policy': {
            'retention_days': retention_days,
            'owner_clear_required': True,
            'clear_ledger_required': True,
            'critical_items_should_be_exported_before_clear': True,
        },
        'total_items': len(items),
        'dated_items': dated,
        'older_than_retention': old_count,
        'clear_ledger_count': len(_safe_list(_safe_dict(data).get('audit_clear_ledger'))),
        'recommendations': ['export_before_clear'] if old_count else [],
    }


def build_audit_tamper_warning_report(data: dict) -> dict:
    items = _audit_items(data)
    chain = enrich_audit_chain(items)
    immutability = audit_immutability_report(data)
    warnings = []
    if not items:
        warnings.append('audit_empty')
    missing_time = len([x for x in items if not (x.get('time') or x.get('created_at') or x.get('timestamp'))])
    if missing_time:
        warnings.append('audit_items_missing_time')
    missing_identity = len([x for x in items if not x.get('user')])
    if missing_identity:
        warnings.append('audit_items_missing_user')
    content_hash = hashlib.sha256(json.dumps(chain, ensure_ascii=False, sort_keys=True, default=str).encode('utf-8')).hexdigest()
    return {
        'status': 'ok' if not warnings else 'review',
        'generated_at': now_iso(),
        'warnings': warnings,
        'items': len(items),
        'chain_last_hash': chain[-1]['hash'] if chain else None,
        'content_hash': content_hash,
        'immutability': immutability,
        'policy': {'hash_chain_available': True, 'runtime_json_not_tamper_proof': True, 'export_manifest_required': True},
    }


def build_logs_operational_summary(data: dict) -> dict:
    logs = _log_items(data)
    levels = Counter(str(x.get('level') or 'info').lower() for x in logs)
    events = Counter(str(x.get('event') or x.get('source') or 'system') for x in logs)
    critical = [x for x in logs if str(x.get('level') or '').lower() in {'error', 'critical'}]
    warnings = [x for x in logs if str(x.get('level') or '').lower() in {'warn', 'warning'}]
    return {
        'status': 'ok' if not critical else 'review',
        'generated_at': now_iso(),
        'total': len(logs),
        'levels': dict(levels),
        'top_events': events.most_common(15),
        'critical_count': len(critical),
        'warning_count': len(warnings),
        'recent_critical': list(reversed(critical[-20:])),
        'policy': {'read_only': True},
    }


def build_level1_50_quality_report(data: dict, settings: dict | None = None) -> dict:
    observability = build_observability_final_report(data, settings)
    audit_search = build_audit_search_final(data, limit=100)
    retention = build_audit_retention_report(data)
    tamper = build_audit_tamper_warning_report(data)
    logs = build_logs_operational_summary(data)
    required = [observability, audit_search, retention, tamper, logs]
    status = 'ok' if all(x.get('status') in {'ok', 'review'} for x in required) else 'blocked'
    return {
        'status': status,
        'revision': LEVEL1_REVISION,
        'generated_at': now_iso(),
        'observability': observability,
        'audit_search': audit_search,
        'retention': retention,
        'tamper_warning': tamper,
        'logs': logs,
        'policy': {'read_only': True, 'no_real_trade_side_effect': True, 'runtime_safe': True},
    }
