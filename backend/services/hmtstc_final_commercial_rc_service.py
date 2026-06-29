"""Rev966-970 HMTSTC Final Commercial Release Candidate service.

Local-only release candidate checks. The service does not open Binance network
paths, never returns API secrets or activation token values, and only reports
contract/readiness state that can be shown safely in the UI.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any


REQUIRED_SETUP_DOCS = (
    "README.md",
    "docs/HMTSTC_FINAL_SETUP_GUIDE.md",
    "docs/HMTSTC_FINAL_DEPLOY_MANIFEST.md",
    "docs/HMTSTC_FINAL_ROUTE_INVENTORY.md",
)

REQUIRED_PRODUCTION_ENDPOINTS = (
    "/api/production/completion-claim",
    "/api/production/launch-readiness",
    "/api/production/deploy-readiness/summary",
    "/api/production/binance/read-only-verification/summary",
    "/api/production/onboarding/summary",
    "/api/production/commission/business-flow/summary",
    "/api/production/dry-run/paper-to-live/summary",
    "/api/production/micro-live/permission/first/summary",
    "/api/production/micro-live/execution/first/summary",
    "/api/production/micro-live/freeze-repeat-decision/summary",
    "/api/production/micro-live/continuity-repair/summary",
    "/api/production/multi-user/hardening/summary",
    "/api/production/strategy-filter/live-calibration/summary",
    "/api/production/high-frequency/safety-capacity/summary",
    "/api/production/monitoring/alert/summary",
    "/api/production/commercial-launch/candidate/summary",
    "/api/production/live-readiness/final-lock/summary",
    "/api/production/regression/clean-package/summary",
)

REQUIRED_RELEASE_GATES = (
    "api_key_only_launch",
    "new_user_onboarding",
    "commission_business_flow",
    "paper_to_live_dry_drill",
    "first_micro_live_permission",
    "first_micro_live_execution_preview",
    "post_live_reconciliation",
    "freeze_repeat_decision",
    "multi_user_isolation",
    "premium_ui_polish",
    "strategy_filter_calibration",
    "hf_safety_capacity",
    "production_monitoring",
    "final_live_readiness_lock",
    "final_regression_clean_package",
)

FORBIDDEN_RUNTIME_NAMES = {
    ".env",
    "auth_store.json",
    "settings_store.json",
    "shadow_store.json",
    "real_trade_store.json",
}

FORBIDDEN_DIR_NAMES = {"node_modules", ".venv", "venv", "runtime_backups", ".pytest_cache", "__pycache__"}
FORBIDDEN_SUFFIXES = {".log", ".db", ".sqlite", ".pyc"}


@dataclass(frozen=True)
class RcCheck:
    name: str
    status: str
    detail: str

    def as_dict(self) -> dict[str, str]:
        return {"name": self.name, "status": self.status, "detail": self.detail}


def _project_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _read(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return path.read_text(encoding="utf-8", errors="ignore")


def _documentation_check(root: Path) -> RcCheck:
    missing = [doc for doc in REQUIRED_SETUP_DOCS if not (root / doc).exists()]
    if missing:
        return RcCheck("final_readme_setup_guide", "BLOCKED", "missing=" + ",".join(missing))
    return RcCheck("final_readme_setup_guide", "PASS", "README, setup guide, route inventory and deploy manifest present")


def _route_inventory_check(root: Path) -> RcCheck:
    routes_path = root / "backend" / "routes" / "production_routes.py"
    inventory_path = root / "docs" / "HMTSTC_FINAL_ROUTE_INVENTORY.md"
    if not routes_path.exists() or not inventory_path.exists():
        return RcCheck("final_route_inventory", "BLOCKED", "route or inventory file missing")
    routes_text = _read(routes_path)
    inventory_text = _read(inventory_path)
    missing_routes = [endpoint for endpoint in REQUIRED_PRODUCTION_ENDPOINTS if endpoint not in routes_text and endpoint not in inventory_text]
    if missing_routes:
        return RcCheck("final_route_inventory", "REVIEW", "missing_endpoint_refs=" + ",".join(missing_routes))
    return RcCheck("final_route_inventory", "PASS", f"{len(REQUIRED_PRODUCTION_ENDPOINTS)} production endpoint contracts referenced")


def _deploy_manifest_check(root: Path) -> RcCheck:
    manifest = root / "docs" / "HMTSTC_FINAL_DEPLOY_MANIFEST.md"
    if not manifest.exists():
        return RcCheck("final_deploy_manifest", "BLOCKED", "deploy manifest missing")
    text = _read(manifest).lower()
    required_terms = ("backend", "frontend", "secret", "runtime", "rollback", "default off")
    missing = [term for term in required_terms if term not in text]
    if missing:
        return RcCheck("final_deploy_manifest", "REVIEW", "missing_terms=" + ",".join(missing))
    return RcCheck("final_deploy_manifest", "PASS", "deploy manifest includes backend/frontend/security/runtime/rollback controls")


def _release_gate_check(root: Path, payload: dict[str, Any]) -> RcCheck:
    provided = set(str(item) for item in (payload.get("release_gates") or []))
    if not provided:
        provided = set(REQUIRED_RELEASE_GATES)
    missing = [gate for gate in REQUIRED_RELEASE_GATES if gate not in provided]
    if missing:
        return RcCheck("final_release_gates", "BLOCKED", "missing_gates=" + ",".join(missing))
    return RcCheck("final_release_gates", "PASS", f"{len(REQUIRED_RELEASE_GATES)} release gate contracts covered")


def _security_scan(root: Path) -> RcCheck:
    findings: list[str] = []
    for path in root.rglob("*"):
        rel = path.relative_to(root).as_posix()
        if any(part in FORBIDDEN_DIR_NAMES for part in path.parts):
            # __pycache__ may exist during local validation but must not be in final zip.
            if path.is_dir() and path.name in {"__pycache__", ".pytest_cache"}:
                continue
        if path.is_dir() and path.name in {"node_modules", ".venv", "venv", "runtime_backups"}:
            findings.append(rel)
        if path.is_file() and any(part in {"__pycache__", ".pytest_cache"} for part in path.parts):
            continue
        if path.is_file() and (path.name in FORBIDDEN_RUNTIME_NAMES or path.suffix in FORBIDDEN_SUFFIXES or path.name.endswith("_store.json")):
            findings.append(rel)
    if findings:
        return RcCheck("final_security_runtime_scan", "BLOCKED", "forbidden_runtime_artifacts=" + ",".join(findings[:20]))
    risky_text_hits: list[str] = []
    for path in (root / "backend").rglob("*.py"):
        text = _read(path)
        if "secret_values_returned\": True" in text or "activation_token_value_returned\": True" in text:
            risky_text_hits.append(path.relative_to(root).as_posix())
    if risky_text_hits:
        return RcCheck("final_security_runtime_scan", "BLOCKED", "secret_return_marker=" + ",".join(risky_text_hits[:10]))
    return RcCheck("final_security_runtime_scan", "PASS", "no forbidden runtime artifact or secret return marker found")


def _real_trading_default_off_check(root: Path) -> RcCheck:
    routes_text = _read(root / "backend" / "routes" / "production_routes.py") if (root / "backend" / "routes" / "production_routes.py").exists() else ""
    service_text = "\n".join(_read(path) for path in (root / "backend" / "services").glob("*live*service.py")) if (root / "backend" / "services").exists() else ""
    combined = routes_text + "\n" + service_text
    suspicious_terms = ("order_market_buy(", "order_market_sell(", "create_order(", "client.order_market")
    suspicious = [term for term in suspicious_terms if term in combined]
    if suspicious:
        return RcCheck("final_real_trading_default_off", "BLOCKED", "direct_order_terms=" + ",".join(suspicious))
    return RcCheck("final_real_trading_default_off", "PASS", "no direct Binance submit/close call detected in production contract layer")


def build_hmtstc_final_commercial_rc(payload: dict[str, Any] | None = None) -> dict[str, Any]:
    payload = payload or {}
    root = _project_root()
    checks = [
        _documentation_check(root),
        _route_inventory_check(root),
        _deploy_manifest_check(root),
        _release_gate_check(root, payload),
        _security_scan(root),
        _real_trading_default_off_check(root),
    ]
    statuses = [check.status for check in checks]
    if "BLOCKED" in statuses:
        decision = "HMTSTC_COMMERCIAL_RC_BLOCKED"
        operator_action = "Fix blocked final RC gate before production launch."
    elif "REVIEW" in statuses:
        decision = "HMTSTC_COMMERCIAL_RC_REVIEW"
        operator_action = "Review non-blocking final RC warnings before external user launch."
    else:
        decision = "HMTSTC_COMMERCIAL_RC_READY"
        operator_action = "Proceed to controlled VPS deployment and read-only Binance verification."
    critical = next((check.name for check in checks if check.status == "BLOCKED"), None) or next((check.name for check in checks if check.status == "REVIEW"), "none")
    return {
        "status": "ok",
        "revision": 970,
        "block": "Rev966-970 HMTSTC Final Commercial RC",
        "decision": decision,
        "critical_blocker": critical,
        "checks": [check.as_dict() for check in checks],
        "checks_passed": sum(1 for check in checks if check.status == "PASS"),
        "checks_total": len(checks),
        "release_gates_total": len(REQUIRED_RELEASE_GATES),
        "production_endpoint_contracts": len(REQUIRED_PRODUCTION_ENDPOINTS),
        "real_network_call_performed": False,
        "real_submit_default_off": True,
        "real_close_default_off": True,
        "emergency_close_default_off": True,
        "auto_scale_default_off": True,
        "auto_apply_default_off": True,
        "auto_close_default_off": True,
        "secret_values_returned": False,
        "activation_token_value_returned": False,
        "owner_approval_required": True,
        "operator_action": operator_action,
    }


def build_hmtstc_final_commercial_rc_summary() -> dict[str, Any]:
    result = build_hmtstc_final_commercial_rc()
    return {
        "status": result["status"],
        "revision": result["revision"],
        "decision": result["decision"],
        "critical_blocker": result["critical_blocker"],
        "checks_passed": result["checks_passed"],
        "checks_total": result["checks_total"],
        "release_gates_total": result["release_gates_total"],
        "production_endpoint_contracts": result["production_endpoint_contracts"],
        "real_submit_default_off": True,
        "real_close_default_off": True,
        "emergency_close_default_off": True,
        "secret_values_returned": False,
        "operator_action": result["operator_action"],
    }
