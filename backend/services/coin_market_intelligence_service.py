from __future__ import annotations

from collections import Counter
from copy import deepcopy
from datetime import datetime, timezone
from statistics import mean
from typing import Any

from services.coin_universe_final_service import build_coin_universe_summary, build_scan_history, build_scan_replay
from services.market_intelligence_final_service import (
    build_market_intelligence_final_report,
    build_market_regime_strategy_match,
    build_no_trade_cooldown_final,
)


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace('+00:00','Z')


def _safe_float(value: Any, fallback: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return fallback


def _safe_int(value: Any, fallback: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return fallback


def _last_scan(data: dict | None) -> dict:
    data = data if isinstance(data, dict) else {}
    scan = data.get('last_scan') if isinstance(data.get('last_scan'), dict) else {}
    return deepcopy(scan)


def _rows(scan: dict) -> list[dict]:
    rows = scan.get('scan_rows') or scan.get('candidates') or []
    return list(rows) if isinstance(rows, list) else []


def _reason_list(row: dict) -> list[str]:
    reasons = row.get('rejection_reasons') or row.get('tradability_reasons') or row.get('reasons') or []
    if isinstance(reasons, str):
        reasons = [reasons]
    if not reasons and row.get('reason'):
        reasons = [row.get('reason')]
    return [str(r) for r in reasons if r]


def build_coin_universe_schema() -> dict:
    return {
        'status': 'ok',
        'revision': 51,
        'schema': 'rev51.coin-universe.v1',
        'funnel_order': ['total_symbols', 'excluded_symbols', 'eligible_symbols', 'deep_analyzed_symbols', 'candidate_symbols'],
        'required_blocks': ['schema', 'funnel', 'exclusions', 'history', 'replay', 'regime', 'no_trade', 'strategy_suppression'],
        'read_only': True,
        'policy': 'Coin universe ve market intelligence yalnızca raporlama/karar destek üretir; order, unlock, pilot veya settings mutate etmez.',
    }


def build_coin_universe_funnel(data: dict | None, settings: dict | None = None) -> dict:
    scan = _last_scan(data)
    base = build_coin_universe_summary(scan)
    total = _safe_int(base.get('total_binance_usdt_pairs'))
    eligible = _safe_int(base.get('eligible_spot_universe'))
    deep = _safe_int(base.get('deep_analyzed_count'))
    candidate = _safe_int(base.get('candidate_count'))
    rejected = max(0, _safe_int(base.get('reject_count')) or (total - eligible))
    exclusions = base.get('reject_reason_distribution') or {}
    top_reason = next(iter(exclusions), None)
    funnel = [
        {'key': 'total_symbols', 'label': 'Total symbols', 'value': total, 'pct_of_total': 100 if total else 0},
        {'key': 'excluded_symbols', 'label': 'Excluded symbols', 'value': rejected, 'pct_of_total': round(rejected / total * 100, 2) if total else 0},
        {'key': 'eligible_symbols', 'label': 'Eligible symbols', 'value': eligible, 'pct_of_total': round(eligible / total * 100, 2) if total else 0},
        {'key': 'deep_analyzed_symbols', 'label': 'Deep analyzed', 'value': deep, 'pct_of_total': round(deep / total * 100, 2) if total else 0},
        {'key': 'candidate_symbols', 'label': 'Candidates', 'value': candidate, 'pct_of_total': round(candidate / total * 100, 2) if total else 0},
    ]
    return {
        'status': 'ok' if total or eligible or candidate else 'waiting_for_scan',
        'generated_at': now_iso(),
        'scan_id': base.get('scan_id'),
        'funnel': funnel,
        'totals': {'total': total, 'excluded': rejected, 'eligible': eligible, 'deep_analyzed': deep, 'candidate': candidate},
        'exclusions': exclusions,
        'main_exclusion_reason': top_reason or 'not_available',
        'quality_distribution': base.get('quality_distribution') or {},
        'analysis_depth_distribution': base.get('analysis_depth_distribution') or {},
        'avg_quality_score': base.get('avg_quality_score') or 0,
        'read_only': True,
    }


def build_scan_history_final(data: dict | None, limit: int = 50) -> dict:
    result = build_scan_history(deepcopy(data or {}), limit=limit)
    result['revision'] = 51
    result['read_only'] = True
    return result


def build_scan_replay_final(data: dict | None, scan_id: str | None = None) -> dict:
    result = build_scan_replay(deepcopy(data or {}), scan_id=scan_id)
    result['revision'] = 51
    result['read_only'] = True
    return result


def build_market_regime_final(data: dict | None, settings: dict | None = None) -> dict:
    match = build_market_regime_strategy_match(deepcopy(data or {}), deepcopy(settings or {}))
    confidence = _safe_float(match.get('confidence'))
    regime = match.get('regime') or 'UNKNOWN'
    return {
        'status': match.get('status') or ('ok' if confidence >= 55 else 'review'),
        'revision': 51,
        'regime': regime,
        'confidence': round(confidence, 2),
        'risk_posture': match.get('risk_posture') or 'review',
        'no_trade_bias': bool(match.get('no_trade_bias')),
        'preferred_strategies': match.get('preferred_strategies') or [],
        'suppressed_strategies': match.get('suppressed_strategies') or [],
        'reason': match.get('reason') or 'Market regime final sınıflandırması üretildi.',
        'read_only': True,
        'updated_at': now_iso(),
    }


def build_no_trade_reason_matrix(data: dict | None, settings: dict | None = None) -> dict:
    no_trade = build_no_trade_cooldown_final(deepcopy(data or {}), deepcopy(settings or {}))
    blockers = list(no_trade.get('blockers') or [])
    rows = []
    for reason in blockers:
        rows.append({'reason': reason, 'active': True, 'severity': 'blocked' if reason in {'emergency_lock', 'market_regime_no_trade_bias'} else 'review', 'source': 'market_intelligence'})
    if not rows:
        rows.append({'reason': 'no_active_no_trade_blocker', 'active': False, 'severity': 'ok', 'source': 'market_intelligence'})
    return {
        'status': 'blocked' if blockers else 'ok',
        'revision': 51,
        'no_trade_active': bool(blockers),
        'cooldown_minutes': no_trade.get('cooldown_minutes') or 0,
        'matrix': rows,
        'read_only': True,
    }


def build_strategy_suppression_matrix(data: dict | None, settings: dict | None = None) -> dict:
    regime = build_market_regime_final(data, settings)
    scan = _last_scan(data)
    rows = _rows(scan)
    weak_quality = 0
    for row in rows:
        if _safe_float(row.get('quality_score') or row.get('score')) < 40:
            weak_quality += 1
    suppressed = []
    for name in regime.get('suppressed_strategies') or []:
        suppressed.append({'strategy': name, 'suppressed': True, 'reason': f"market_regime:{regime.get('regime')}", 'severity': 'blocked' if regime.get('no_trade_bias') else 'review'})
    if rows and weak_quality / max(len(rows), 1) > 0.55:
        suppressed.append({'strategy': 'real_trade_entries', 'suppressed': True, 'reason': 'coin_quality_environment_weak', 'severity': 'review'})
    if not suppressed:
        suppressed.append({'strategy': 'no_strategy_suppressed', 'suppressed': False, 'reason': 'market_allows_watch_mode', 'severity': 'ok'})
    return {
        'status': 'blocked' if any(x.get('severity') == 'blocked' for x in suppressed) else ('review' if any(x.get('suppressed') for x in suppressed) else 'ok'),
        'revision': 51,
        'regime': regime.get('regime'),
        'suppression_count': sum(1 for x in suppressed if x.get('suppressed')),
        'matrix': suppressed,
        'read_only': True,
    }


def build_market_visibility_summary(data: dict | None, settings: dict | None = None) -> dict:
    funnel = build_coin_universe_funnel(data, settings)
    regime = build_market_regime_final(data, settings)
    no_trade = build_no_trade_reason_matrix(data, settings)
    suppression = build_strategy_suppression_matrix(data, settings)
    return {
        'status': 'blocked' if no_trade.get('status') == 'blocked' else ('review' if regime.get('status') == 'review' or suppression.get('status') == 'review' else 'ok'),
        'revision': 51,
        'generated_at': now_iso(),
        'funnel': funnel,
        'regime': regime,
        'no_trade': no_trade,
        'suppression': suppression,
        'summary_cards': {
            'total_symbols': (funnel.get('totals') or {}).get('total', 0),
            'candidate_symbols': (funnel.get('totals') or {}).get('candidate', 0),
            'market_regime': regime.get('regime'),
            'no_trade_active': no_trade.get('no_trade_active'),
            'suppression_count': suppression.get('suppression_count'),
        },
        'read_only': True,
    }


def build_coin_market_intelligence_quality(data: dict | None, settings: dict | None = None) -> dict:
    schema = build_coin_universe_schema()
    funnel = build_coin_universe_funnel(data, settings)
    history = build_scan_history_final(data)
    replay = build_scan_replay_final(data)
    regime = build_market_regime_final(data, settings)
    no_trade = build_no_trade_reason_matrix(data, settings)
    suppression = build_strategy_suppression_matrix(data, settings)
    visibility = build_market_visibility_summary(data, settings)
    checks = {
        'schema_ok': schema.get('status') == 'ok',
        'funnel_has_contract': all(k in (funnel.get('totals') or {}) for k in ['total', 'excluded', 'eligible', 'deep_analyzed', 'candidate']),
        'history_ok': history.get('status') == 'ok',
        'replay_read_only': replay.get('read_only') is True,
        'regime_has_value': bool(regime.get('regime')),
        'no_trade_matrix_present': bool(no_trade.get('matrix')),
        'suppression_matrix_present': bool(suppression.get('matrix')),
        'visibility_read_only': visibility.get('read_only') is True,
    }
    failed = [name for name, ok in checks.items() if not ok]
    return {
        'status': 'ok' if not failed else 'review',
        'revision': 51,
        'checks': checks,
        'failed_checks': failed,
        'coverage': ['coin_universe_schema', 'funnel', 'scan_history', 'scan_replay', 'market_regime', 'no_trade_matrix', 'strategy_suppression', 'summary_dashboard_visibility'],
        'read_only': True,
        'generated_at': now_iso(),
    }
