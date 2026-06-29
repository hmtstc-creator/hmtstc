from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
from hashlib import sha256
from typing import Any

from services.autonomous_operator_free_dashboard_service import build_autonomous_operator_free_dashboard


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _safe_bool(value: Any, fallback: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "on", "enabled", "allow", "ready", "ok"}
    if value is None:
        return fallback
    return bool(value)


def _safe_float(value: Any, fallback: float = 0.0) -> float:
    try:
        if value is None or value == "":
            return fallback
        return float(value)
    except (TypeError, ValueError):
        return fallback


def _policy(settings: dict | None) -> dict:
    settings = settings if isinstance(settings, dict) else {}
    raw = settings.get("autonomous_production_go_live_candidate") if isinstance(settings.get("autonomous_production_go_live_candidate"), dict) else {}
    return {
        "enabled": _safe_bool(raw.get("enabled"), True),
        "required_source_revision": 99,
        "network_calls_allowed": _safe_bool(raw.get("network_calls_allowed"), False),
        "direct_order_enabled": _safe_bool(raw.get("direct_order_enabled"), False),
        "real_submit_enabled": _safe_bool(raw.get("real_submit_enabled"), False),
        "runtime_write_enabled": _safe_bool(raw.get("runtime_write_enabled"), False),
        "require_manual_go_live_approval": _safe_bool(raw.get("require_manual_go_live_approval"), True),
        "require_emergency_rehearsal": _safe_bool(raw.get("require_emergency_rehearsal"), True),
        "required_branch": str(raw.get("required_branch") or "main"),
        "expected_vps_service": str(raw.get("expected_vps_service") or "hmtstc"),
        "max_go_live_daily_loss_usdt": min(-0.1, _safe_float(raw.get("max_go_live_daily_loss_usdt"), -5.0)),
    }


def _source(data: dict, settings: dict, auth_store: dict, username: str) -> dict:
    raw = data.get("autonomous_operator_free_dashboard") if isinstance(data.get("autonomous_operator_free_dashboard"), dict) else None
    if raw and raw.get("revision") == 99 and "control_actions" in raw:
        return raw
    return build_autonomous_operator_free_dashboard(data, settings, auth_store, username)


def _check(name: str, status: str, detail: str, required: bool = True) -> dict:
    return {"name": name, "status": status, "required": required, "detail": detail}


def _ok(value: Any) -> bool:
    return str(value or "").strip().lower() in {"ok", "ready", "pass", "passed", "healthy", "clean", "available", "enabled"}


def _auth_user(auth_store: dict, username: str) -> dict:
    if not isinstance(auth_store, dict):
        return {}
    users = auth_store.get("users") if isinstance(auth_store.get("users"), dict) else {}
    raw = users.get(username) if isinstance(users.get(username), dict) else {}
    return raw


def _live_safety_checks(source: dict, policy: dict) -> list[dict]:
    command = source.get("command_preview") if isinstance(source.get("command_preview"), dict) else {}
    controls = source.get("control_actions") if isinstance(source.get("control_actions"), dict) else {}
    safety = source.get("safety_contract") if isinstance(source.get("safety_contract"), dict) else {}
    return [
        _check("direct_order_default_off", "ok" if command.get("places_order") is False and not policy["direct_order_enabled"] else "blocked", "Direct order placement must remain OFF until explicit go-live switch."),
        _check("exchange_request_default_off", "ok" if command.get("sends_exchange_request") is False and not policy["network_calls_allowed"] else "blocked", "No exchange request is allowed in Rev100 candidate checks."),
        _check("real_submit_default_off", "ok" if command.get("real_submit_enabled") is False and not policy["real_submit_enabled"] else "blocked", "Real submit remains OFF by default."),
        _check("runtime_write_default_off", "ok" if command.get("writes_runtime_state") is False and not policy["runtime_write_enabled"] else "blocked", "Production candidate report is read-only."),
        _check("emergency_stop_surface", "ok" if "emergency_stop" in controls else "review", "Owner emergency stop control must exist."),
        _check("safe_mode_surface", "ok" if "safe_mode" in controls else "review", "Owner safe-mode control must exist."),
        _check("owner_control_approval_gated", "ok" if safety.get("owner_controls_require_explicit_click") is True else "review", "Owner controls must be explicit click/approval gated."),
    ]


def _vps_checks(data: dict, policy: dict) -> list[dict]:
    vps = data.get("vps") if isinstance(data.get("vps"), dict) else {}
    service_name = str(vps.get("service_name") or policy["expected_vps_service"])
    service_status = str(vps.get("service_status") or data.get("vps_service_status") or "manual_verify_required")
    health_status = str(vps.get("health_endpoint_status") or data.get("health_endpoint_status") or "manual_verify_required")
    return [
        _check("vps_service_name", "ok" if service_name == policy["expected_vps_service"] else "review", f"Expected service: {policy['expected_vps_service']}, found: {service_name}"),
        _check("vps_service_status", "ok" if _ok(service_status) else "review", f"VPS service status: {service_status}"),
        _check("health_endpoint", "ok" if _ok(health_status) else "review", f"Health endpoint status: {health_status}"),
    ]


def _github_checks(data: dict, policy: dict) -> list[dict]:
    git = data.get("github") if isinstance(data.get("github"), dict) else {}
    branch = str(git.get("branch") or policy["required_branch"])
    clean = _safe_bool(git.get("clean_worktree"), False)
    remote = str(git.get("remote_status") or "manual_verify_required")
    return [
        _check("github_branch", "ok" if branch == policy["required_branch"] else "review", f"Required branch: {policy['required_branch']}, current: {branch}"),
        _check("github_clean_worktree", "ok" if clean else "review", "Working tree must be clean before VPS deploy."),
        _check("github_remote_sync", "ok" if _ok(remote) else "review", f"Remote sync status: {remote}"),
    ]


def _secret_checks(auth_store: dict, username: str) -> list[dict]:
    user_auth = _auth_user(auth_store, username)
    serialized = repr(user_auth).lower()
    risky_terms = ["secret_key=", "api_secret=", "private_key", "-----begin", "password="]
    plaintext_risk = any(term in serialized for term in risky_terms)
    has_trade_permission = _safe_bool(user_auth.get("trade_permission") or user_auth.get("can_trade"), False)
    has_read_permission = _safe_bool(user_auth.get("read_permission") or user_auth.get("can_read"), bool(user_auth))
    return [
        _check("secret_plaintext_scan", "ok" if not plaintext_risk else "blocked", "No plaintext secret/key material may be exposed by API payloads."),
        _check("read_permission_visibility", "ok" if has_read_permission or not user_auth else "review", "Read permission should be visible for final readiness."),
        _check("trade_permission_guarded", "ok" if not has_trade_permission or user_auth.get("owner_confirmed") is True else "review", "Trade permission requires owner confirmation before real lane."),
    ]


def _runtime_checks(data: dict, policy: dict) -> list[dict]:
    manifest = data.get("package_manifest") if isinstance(data.get("package_manifest"), dict) else {}
    leak_status = str(data.get("runtime_leak_status") or manifest.get("runtime_leak_status") or "ok")
    excluded = manifest.get("excluded_runtime_files") if isinstance(manifest.get("excluded_runtime_files"), list) else []
    return [
        _check("runtime_leak_guard", "ok" if _ok(leak_status) else "blocked", f"Runtime leak guard: {leak_status}"),
        _check("runtime_write_guard", "ok" if not policy["runtime_write_enabled"] else "blocked", "Runtime writes remain disabled in candidate report."),
        _check("runtime_exclusion_policy", "ok" if excluded or not manifest else "review", "Runtime/secret files must be excluded from release zip."),
    ]


def _emergency_rehearsal_checks(data: dict, source: dict, policy: dict) -> list[dict]:
    rehearsal = data.get("emergency_rehearsal") if isinstance(data.get("emergency_rehearsal"), dict) else {}
    status = str(rehearsal.get("status") or data.get("emergency_rehearsal_status") or "manual_rehearsal_required")
    controls = source.get("control_actions") if isinstance(source.get("control_actions"), dict) else {}
    emergency_available = "emergency_stop" in controls
    if not policy["require_emergency_rehearsal"]:
        required_status = "ok"
    else:
        required_status = "ok" if _ok(status) else "review"
    return [
        _check("emergency_stop_available", "ok" if emergency_available else "blocked", "Emergency stop control must be present."),
        _check("emergency_close_rehearsal", required_status, f"Emergency rehearsal status: {status}"),
        _check("safe_mode_rehearsal", "ok" if "safe_mode" in controls else "review", "Safe mode action must be visible before production."),
    ]


def _flatten(checks: dict[str, list[dict]]) -> list[dict]:
    rows: list[dict] = []
    for section, items in checks.items():
        for item in items:
            row = dict(item)
            row["section"] = section
            rows.append(row)
    return rows


def build_autonomous_production_go_live_candidate(
    data: dict | None,
    settings: dict | None = None,
    auth_store: dict | None = None,
    username: str = "default",
) -> dict:
    """Rev100 production go-live candidate controller.

    This is the final read-only production readiness layer. It compiles the
    autonomous dashboard, safety checklist, VPS/GitHub readiness, secret/runtime
    scans, real API permission scan, emergency rehearsal and a final go/no-go
    report without placing orders, calling an exchange, or writing runtime state.
    """
    data = deepcopy(data or {})
    settings = deepcopy(settings or {})
    auth_store = deepcopy(auth_store or {})
    policy = _policy(settings)
    source = _source(data, settings, auth_store, username)

    checks = {
        "autonomous_chain": [
            _check("source_revision_99", "ok" if source.get("revision") == policy["required_source_revision"] else "blocked", "Rev99 operator-free dashboard must feed Rev100."),
            _check("operator_dashboard_not_blocked", "ok" if source.get("status") != "blocked" else "blocked", f"Operator dashboard status: {source.get('status', 'unknown')}"),
            _check("five_summary_tiles_present", "ok" if len(source.get("visible_tiles") or []) == 5 else "review", "Summary must remain compressed to five owner-facing tiles."),
        ],
        "live_safety_checklist": _live_safety_checks(source, policy),
        "vps_service_check": _vps_checks(data, policy),
        "github_sync_check": _github_checks(data, policy),
        "secret_leak_scan": _secret_checks(auth_store, username),
        "runtime_persistence_scan": _runtime_checks(data, policy),
        "real_api_permission_scan": [
            _check("real_api_secret_layer_present", "ok" if isinstance(auth_store, dict) else "review", "User API secret layer must be readable without exposing plaintext."),
            _check("real_submit_manual_enable_required", "ok" if not policy["real_submit_enabled"] else "blocked", "Real submit requires explicit enable flag outside this report."),
            _check("daily_loss_hard_stop_defined", "ok" if policy["max_go_live_daily_loss_usdt"] < 0 else "blocked", "Daily loss hard stop must be negative and enforced."),
        ],
        "emergency_close_rehearsal": _emergency_rehearsal_checks(data, source, policy),
    }
    rows = _flatten(checks)
    blockers = [row for row in rows if row.get("required") and row.get("status") == "blocked"]
    reviews = [row for row in rows if row.get("status") == "review"]
    warnings: list[str] = []
    if reviews:
        warnings.append("manual_production_readiness_items_remain")
    if not policy["enabled"]:
        blockers.append(_check("production_candidate_disabled", "blocked", "Rev100 production candidate policy is disabled."))
    if policy["network_calls_allowed"] or policy["direct_order_enabled"] or policy["real_submit_enabled"]:
        blockers.append(_check("unsafe_submit_flags_enabled", "blocked", "Network/direct/real submit flags must remain OFF in Rev100 report."))

    go_no_go = "GO_CANDIDATE" if not blockers and not reviews else ("NO_GO" if blockers else "REVIEW_READY")
    status = "ok" if go_no_go == "GO_CANDIDATE" else ("blocked" if blockers else "review")
    evidence_seed = f"rev100|{username}|{source.get('generated_at')}|{go_no_go}|{len(blockers)}|{len(reviews)}"
    return {
        "status": status,
        "revision": 100,
        "engine": "autonomous_production_go_live_candidate",
        "generated_at": now_iso(),
        "source_revision": source.get("revision"),
        "source_status": source.get("status"),
        "production_candidate": True,
        "go_no_go": go_no_go,
        "go_live_mode": "candidate_read_only",
        "check_sections": checks,
        "check_totals": {
            "total": len(rows),
            "ok": len([row for row in rows if row.get("status") == "ok"]),
            "review": len(reviews),
            "blocked": len(blockers),
        },
        "blockers": [row.get("name") for row in blockers],
        "warnings": warnings,
        "final_report": {
            "decision": go_no_go,
            "summary": "production_candidate_clear" if go_no_go == "GO_CANDIDATE" else ("blocked_items_must_be_fixed" if blockers else "manual_vps_github_rehearsal_verification_required"),
            "required_next_action": "manual_owner_go_live_approval" if go_no_go == "GO_CANDIDATE" and policy["require_manual_go_live_approval"] else "resolve_review_or_blocked_items",
            "direct_order_placement": False,
            "exchange_request": False,
            "runtime_write": False,
        },
        "command_preview": {
            "type": "production_go_live_candidate_report",
            "read_only": True,
            "places_order": False,
            "sends_exchange_request": False,
            "writes_runtime_state": False,
            "direct_order_enabled": False,
            "real_submit_enabled": False,
            "requires_manual_owner_approval": policy["require_manual_go_live_approval"],
        },
        "safety_contract": {
            "contains_secret": False,
            "direct_order_placement": False,
            "exchange_request": False,
            "runtime_write": False,
            "approval_gated": True,
            "manual_go_live_required": policy["require_manual_go_live_approval"],
        },
        "audit_evidence": {
            "evidence_id": sha256(evidence_seed.encode("utf-8")).hexdigest()[:24],
            "source_engine": source.get("engine"),
            "source_status": source.get("status"),
            "go_no_go": go_no_go,
            "check_total": len(rows),
        },
        "read_only": True,
        "dry_run": True,
    }


def _summary_from_payload(payload: dict) -> dict:
    return {
        "status": payload.get("status", "review"),
        "revision": 100,
        "engine": "autonomous_production_go_live_candidate_summary",
        "generated_at": payload.get("generated_at"),
        "production_candidate": payload.get("production_candidate"),
        "go_no_go": payload.get("go_no_go"),
        "source_revision": payload.get("source_revision"),
        "source_status": payload.get("source_status"),
        "check_totals": payload.get("check_totals") or {},
        "blockers": payload.get("blockers") or [],
        "warnings": payload.get("warnings") or [],
        "final_report": payload.get("final_report") or {},
        "read_only": True,
        "dry_run": True,
        "direct_order_placement": False,
        "exchange_request": False,
        "runtime_write": False,
        "real_submit_enabled": False,
    }


def build_summary_autonomous_production_go_live_candidate(data: dict | None, settings: dict | None = None, auth_store: dict | None = None, username: str = "default") -> dict:
    return _summary_from_payload(build_autonomous_production_go_live_candidate(data, settings, auth_store, username))


def _sample_data() -> dict:
    source = {
        "revision": 99,
        "status": "ok",
        "generated_at": "2026-05-24T00:00:00Z",
        "visible_tiles": [
            {"key": "bot_mode", "value": "CONTROLLED_SCALE"},
            {"key": "market_tradeable", "value": "yes"},
            {"key": "today_pnl", "value": 3.5},
            {"key": "risk", "value": "normal"},
            {"key": "intervention", "value": "none"},
        ],
        "control_actions": {"emergency_stop": {"auto_execute": False}, "safe_mode": {"auto_execute": False}},
        "command_preview": {"read_only": True, "places_order": False, "sends_exchange_request": False, "writes_runtime_state": False, "real_submit_enabled": False},
        "safety_contract": {"owner_controls_require_explicit_click": True, "contains_secret": False},
    }
    return {
        "autonomous_operator_free_dashboard": source,
        "vps": {"service_name": "hmtstc", "service_status": "ok", "health_endpoint_status": "ok"},
        "github": {"branch": "main", "clean_worktree": True, "remote_status": "ok"},
        "package_manifest": {"runtime_leak_status": "ok", "excluded_runtime_files": ["backend/.env", "backend/*_store.json", "runtime_backups/"]},
        "emergency_rehearsal": {"status": "ok"},
    }


def build_autonomous_production_go_live_candidate_quality(data: dict | None = None, settings: dict | None = None, auth_store: dict | None = None, username: str = "default") -> dict:
    sample_auth = {"users": {username: {"read_permission": True, "trade_permission": False, "secret_ref": "masked"}}}
    payload = build_autonomous_production_go_live_candidate(
        data or _sample_data(),
        settings or {"autonomous_production_go_live_candidate": {"enabled": True}},
        auth_store or sample_auth,
        username,
    )
    command = payload.get("command_preview") if isinstance(payload.get("command_preview"), dict) else {}
    totals = payload.get("check_totals") if isinstance(payload.get("check_totals"), dict) else {}
    checks = {
        "revision_is_100": payload.get("revision") == 100,
        "source_revision_is_99": payload.get("source_revision") == 99,
        "go_no_go_report_present": payload.get("go_no_go") in {"GO_CANDIDATE", "REVIEW_READY", "NO_GO"},
        "production_candidate_report_is_read_only": command.get("read_only") is True,
        "does_not_place_order": command.get("places_order") is False,
        "does_not_call_exchange": command.get("sends_exchange_request") is False,
        "does_not_write_runtime": command.get("writes_runtime_state") is False,
        "direct_order_off": command.get("direct_order_enabled") is False,
        "real_submit_off": command.get("real_submit_enabled") is False,
        "safety_sections_present": all(key in payload.get("check_sections", {}) for key in ("live_safety_checklist", "vps_service_check", "github_sync_check", "secret_leak_scan", "runtime_persistence_scan", "real_api_permission_scan", "emergency_close_rehearsal")),
        "all_sample_checks_ok": totals.get("blocked", 1) == 0 and totals.get("review", 1) == 0,
        "summary_revision_is_100": _summary_from_payload(payload).get("revision") == 100,
    }
    passed = all(checks.values())
    return {
        "status": "ok" if passed else "review",
        "revision": 100,
        "engine": "autonomous_production_go_live_candidate_quality",
        "generated_at": now_iso(),
        "quality_status": "PRODUCTION_GO_LIVE_CANDIDATE_OK" if passed else "PRODUCTION_GO_LIVE_CANDIDATE_REVIEW",
        "checks": checks,
        "summary": _summary_from_payload(payload),
        "sample_go_no_go": payload.get("go_no_go"),
        "sample_totals": totals,
    }
