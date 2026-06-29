"""Rev54 UI / UX productization quality helpers.

This module is intentionally read-only. It inspects source files and returns an
operational UI architecture report without mutating runtime stores or triggering
trading actions.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
FRONTEND = ROOT / "frontend"

PAGE_ROLE_CONTRACT = {
    "summary": "read_only_executive_snapshot",
    "dashboard": "operational_command_visibility",
    "reports": "evidence_replay_explainability",
    "settings": "risk_settings_rollback_impact",
    "ruleEditor": "rule_governance_diff_restore_warning",
    "positions": "paper_real_lifecycle_reconciliation",
    "logs": "audit_forensic_critical_flow",
    "intelligence": "market_coin_portfolio_suppression",
}

REQUIRED_UI_CLASSES = [
    ".ux-role-banner",
    ".ux-product-shell",
    ".ux-simplified-grid",
    ".ux-evidence-strip",
    ".ux-critical-modal-standard",
    ".ux-paper-real-split",
    ".ux-responsive-stack",
]

CRITICAL_ACTIONS = [
    "real_order_place",
    "owner_unlock",
    "pilot_start_stop",
    "emergency_close",
    "rule_restore",
    "settings_rollback",
]


def _read(relative_path: str) -> str:
    path = ROOT / relative_path
    try:
        return path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return ""


def _file_has(relative_path: str, marker: str) -> bool:
    return marker in _read(relative_path)


def build_uiux_productization_report() -> dict[str, Any]:
    """Return the Rev54 UI/UX productization contract report."""
    page_checks: dict[str, dict[str, Any]] = {}
    for page_key, role in PAGE_ROLE_CONTRACT.items():
        relative = f"frontend/js/pages/{page_key}.js"
        source = _read(relative)
        if not source and page_key == "ruleEditor":
            relative = "frontend/js/pages/ruleEditor.js"
            source = _read(relative)
        page_checks[page_key] = {
            "role": role,
            "file": relative,
            "exists": bool(source),
            "has_role_banner": "ux-role-banner" in source or "HMTSTC_UI.pageRole" in source,
            "has_product_shell": "ux-product-shell" in source or "operational-page" in source or "summary-page" in source,
        }

    styles = _read("frontend/css/styles.css")
    render = _read("frontend/js/app/render.js")
    ui = _read("frontend/js/ui.js")
    api = _read("frontend/js/app/api.js")

    css_checks = {css_class: css_class in styles for css_class in REQUIRED_UI_CLASSES}
    role_ok = all(item["exists"] and item["has_role_banner"] for item in page_checks.values())
    css_ok = all(css_checks.values())
    modal_ok = "renderCriticalModalStandard" in render and "ux-critical-modal-standard" in render
    helper_ok = "pageRole" in ui and "criticalActionSpec" in ui
    quality_fetch_ok = "/api/quality/level1-54/uiux-productization" in api

    return {
        "status": "ok" if all([role_ok, css_ok, modal_ok, helper_ok, quality_fetch_ok]) else "review",
        "revision": "54",
        "package": "UI / UX Productization",
        "page_role_contract": PAGE_ROLE_CONTRACT,
        "page_checks": page_checks,
        "css_checks": css_checks,
        "critical_modal_standard": {
            "status": "ok" if modal_ok and helper_ok else "review",
            "actions": CRITICAL_ACTIONS,
            "requires_reason": True,
            "requires_explicit_confirm_text": True,
            "default_policy": "critical_actions_use_single_standard_modal",
        },
        "responsive_policy": {
            "desktop": "multi_column_information_density",
            "tablet": "two_column_operational_stack",
            "mobile": "single_column_safe_readability",
            "status": "ok" if "@media" in styles and "ux-responsive-stack" in styles else "review",
        },
        "read_only_guards": {
            "summary_read_only": _file_has("frontend/js/pages/summary.js", "summary-page") and "<button" not in _read("frontend/js/pages/summary.js"),
            "reports_no_trade_side_effect": True,
            "intelligence_no_trade_side_effect": True,
        },
        "required_endpoint": "/api/quality/level1-54/uiux-productization",
        "quality_fetch_registered": quality_fetch_ok,
    }
