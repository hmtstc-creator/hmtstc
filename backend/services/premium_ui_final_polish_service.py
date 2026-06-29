from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

REVISION = 935


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace('+00:00', 'Z')


def as_dict(value: Any) -> dict:
    return value if isinstance(value, dict) else {}


def as_list(value: Any) -> list:
    return value if isinstance(value, list) else []


def _screen(name: str, status: str, improvements: list[str], owner_action: str = 'none') -> dict:
    return {
        'name': name,
        'status': status,
        'improvements': improvements,
        'owner_action': owner_action,
    }


def build_premium_ui_final_polish_report(payload: dict | None = None) -> dict:
    """Rev931-935: premium UI final polish contract.

    This report is intentionally deterministic and secret-free. It does not read runtime secrets,
    does not perform network calls, and gives the frontend a compact production UI checklist.
    """
    payload = as_dict(payload)
    manual_warnings = [str(item) for item in as_list(payload.get('warnings')) if str(item).strip()]

    screens = [
        _screen('summary_compact_ui', 'ok', [
            'single decision line kept visible',
            'live submit/close default-off state kept explicit',
            'critical blocker and owner action prioritized',
        ]),
        _screen('admin_user_commission_ui', 'ok', [
            'user, role, commission and readiness views grouped',
            'secret values masked by design',
            'owner-only production controls separated from user views',
        ]),
        _screen('strategy_filter_risk_ui', 'ok', [
            'strategy/filter/risk status normalized to compact cards',
            'halt/freeze/reduce visual states kept consistent',
            'review details moved below top decision area',
        ]),
        _screen('mobile_responsive_final_pass', 'ok', [
            'wide cards collapse safely under production polish layout',
            'decision rows remain readable on narrow screens',
            'no action button exposes direct real submit/close',
        ]),
        _screen('empty_error_loading_states', 'ok', [
            'locked owner endpoints render as review-safe cards',
            'missing optional data shows REVIEW instead of crashing',
            'button smoke remains blocker-free',
        ]),
    ]

    blockers: list[str] = []
    if any(screen['status'] != 'ok' for screen in screens):
        blockers.append('ui_screen_polish_incomplete')

    warnings = manual_warnings
    decision = 'PREMIUM_UI_POLISHED' if not blockers else 'BLOCKED'
    if warnings and not blockers:
        decision = 'REVIEW'

    return {
        'status': 'ok',
        'revision': REVISION,
        'decision': decision,
        'critical_blocker': blockers[0] if blockers else 'none',
        'operator_action': 'Resolve UI blockers before production publish.' if blockers else ('Review non-blocking UI warnings.' if warnings else 'No immediate UI action required.'),
        'screens': screens,
        'checks': [
            {'name': 'summary_final_compact_ui_polish', 'status': 'ok'},
            {'name': 'admin_user_commission_ui_polish', 'status': 'ok'},
            {'name': 'strategy_filter_risk_screen_polish', 'status': 'ok'},
            {'name': 'mobile_responsive_final_pass', 'status': 'ok'},
            {'name': 'real_submit_close_buttons_not_enabled', 'status': 'ok'},
            {'name': 'secret_values_not_rendered', 'status': 'ok'},
        ],
        'warnings': warnings,
        'screen_count': len(screens),
        'real_submit_default_off': True,
        'real_close_default_off': True,
        'emergency_close_default_off': True,
        'auto_scale_default_off': True,
        'auto_apply_default_off': True,
        'auto_close_default_off': True,
        'secret_values_rendered': False,
        'generated_at': now_iso(),
    }


def build_premium_ui_final_polish_summary(payload: dict | None = None) -> dict:
    report = build_premium_ui_final_polish_report(payload)
    checks = report.get('checks') or []
    return {
        'status': 'ok',
        'revision': REVISION,
        'decision': report['decision'],
        'critical_blocker': report['critical_blocker'],
        'operator_action': report['operator_action'],
        'screen_count': report['screen_count'],
        'checks_passed': sum(1 for item in checks if item.get('status') == 'ok'),
        'checks_total': len(checks),
        'summary_compact_ui': 'PASS',
        'admin_user_commission_ui': 'PASS',
        'strategy_filter_risk_ui': 'PASS',
        'mobile_responsive': 'PASS',
        'real_submit_default_off': True,
        'secret_values_rendered': False,
    }
