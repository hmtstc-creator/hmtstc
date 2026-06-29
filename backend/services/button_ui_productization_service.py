from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
DOCS = ROOT / "docs"
REVISION = 58
REQUIRED_SERVICE_PAGES = [
    "summary",
    "tradingControl",
    "paperLabModels",
    "reportsReplay",
    "strategyGovernance",
    "marketIntelligence",
    "observabilityAudit",
    "settings",
]


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _read_json(path: Path, fallback: dict[str, Any]) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        return payload if isinstance(payload, dict) else fallback
    except Exception:
        return fallback


def build_button_ui_productization_quality() -> dict[str, Any]:
    button_smoke = _read_json(DOCS / "LEVEL1_58_BUTTON_SMOKE_REPORT.json", {})
    inventory = _read_json(DOCS / "LEVEL1_58_BUTTON_INVENTORY.json", {})
    blockers = []
    warnings = []

    if button_smoke.get("result") != "BUTTON_SMOKE_OK":
        blockers.append("button_smoke_not_ok")
    if button_smoke.get("service_menu") != REQUIRED_SERVICE_PAGES:
        blockers.append("service_menu_contract_mismatch")
    if not inventory.get("button_count"):
        blockers.append("button_inventory_missing")
    if (button_smoke.get("warnings") or []):
        warnings.append("button_smoke_has_review_warnings")

    gates = [
        {"name": "button_inventory", "status": "ok" if inventory.get("button_count", 0) > 0 else "blocked", "detail": f"{inventory.get('button_count', 0)} buttons inventoried."},
        {"name": "button_smoke", "status": "ok" if button_smoke.get("result") == "BUTTON_SMOKE_OK" else "blocked", "detail": button_smoke.get("result", "missing")},
        {"name": "service_page_restructure", "status": "ok" if button_smoke.get("service_menu") == REQUIRED_SERVICE_PAGES else "blocked", "detail": "8 service-based pages are registered."},
        {"name": "summary_read_only", "status": "ok" if not any(b.get("gate") == "summary_read_only_source" for b in button_smoke.get("blockers", [])) else "blocked", "detail": "Summary has no action controls."},
        {"name": "settings_scope", "status": "ok" if not any(w.get("gate") == "settings_scope" for w in button_smoke.get("warnings", [])) else "review", "detail": "General Settings separated from rule/model/trade governance."},
    ]
    ok_count = sum(1 for gate in gates if gate["status"] == "ok")
    readiness = round(ok_count / len(gates) * 100, 2)

    return {
        "revision": REVISION,
        "status": "ok" if not blockers else "review",
        "generated_at": _now(),
        "readiness_score": readiness,
        "required_service_pages": REQUIRED_SERVICE_PAGES,
        "gates": gates,
        "button_count": inventory.get("button_count", 0),
        "api_call_count": button_smoke.get("api_call_count", inventory.get("frontend_api_call_count", 0)),
        "backend_route_count": button_smoke.get("backend_route_count", inventory.get("backend_route_count", 0)),
        "blockers": blockers,
        "warnings": warnings,
        "policy": {
            "summary_read_only": True,
            "real_trading_owner_gated": True,
            "runtime_files_excluded_from_release": True,
            "service_based_navigation": True,
        },
    }
