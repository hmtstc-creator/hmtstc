from __future__ import annotations

import os
from copy import deepcopy
from datetime import datetime, timezone
from hashlib import sha256
from typing import Any

from services.autonomous_production_go_live_candidate_service import build_autonomous_production_go_live_candidate


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _safe_bool(value: Any, fallback: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        text = value.strip().lower()
        if text in {"1", "true", "yes", "on", "enabled", "allow", "allowed", "ready", "ok"}:
            return True
        if text in {"0", "false", "no", "off", "disabled", "deny", "blocked", "none"}:
            return False
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
    raw = settings.get("autonomous_live_config_governance") if isinstance(settings.get("autonomous_live_config_governance"), dict) else {}
    return {
        "enabled": _safe_bool(raw.get("enabled"), True),
        "required_source_revision": 100,
        "expected_environment": str(raw.get("expected_environment") or "production_candidate"),
        "config_version": str(raw.get("config_version") or "rev101-safe-default"),
        "owner_confirmation_required": _safe_bool(raw.get("owner_confirmation_required"), True),
        "allow_network_calls": _safe_bool(raw.get("allow_network_calls"), False),
        "allow_direct_orders": _safe_bool(raw.get("allow_direct_orders"), False),
        "allow_real_submit": _safe_bool(raw.get("allow_real_submit"), False),
        "allow_runtime_write": _safe_bool(raw.get("allow_runtime_write"), False),
        "max_micro_notional_usdt": max(1.0, min(_safe_float(raw.get("max_micro_notional_usdt"), 10.0), 25.0)),
        "max_daily_loss_usdt": min(-0.1, _safe_float(raw.get("max_daily_loss_usdt"), -5.0)),
        "required_owner_role": str(raw.get("required_owner_role") or "owner"),
    }


def _source(data: dict, settings: dict, auth_store: dict, username: str) -> dict:
    raw = data.get("autonomous_production_go_live_candidate") if isinstance(data.get("autonomous_production_go_live_candidate"), dict) else None
    if raw and raw.get("revision") == 100 and raw.get("engine") == "autonomous_production_go_live_candidate":
        return raw
    return build_autonomous_production_go_live_candidate(data, settings, auth_store, username)


def _env_bool(name: str, fallback: bool = False) -> bool:
    return _safe_bool(os.environ.get(name), fallback)


def _safe_env_snapshot() -> dict:
    """Return non-secret live config flags only. Secret/key values are never read or returned."""
    names = {
        "HMTSTC_EXCHANGE_NETWORK_ENABLED": False,
        "HMTSTC_DIRECT_ORDER_ENABLED": False,
        "HMTSTC_REAL_SUBMIT_ENABLED": False,
        "HMTSTC_RUNTIME_WRITE_ENABLED": False,
        "HMTSTC_OWNER_CONFIRMATION_REQUIRED": True,
        "HMTSTC_MICRO_REAL_ENABLED": False,
    }
    flags = {name: _env_bool(name, fallback) for name, fallback in names.items()}
    version = str(os.environ.get("HMTSTC_LIVE_CONFIG_VERSION") or "unset")
    env_name = str(os.environ.get("HMTSTC_ENV") or os.environ.get("APP_ENV") or "unset")
    return {
        "flags": flags,
        "config_version_present": version != "unset",
        "config_version_hash": sha256(version.encode("utf-8")).hexdigest()[:12] if version != "unset" else "unset",
        "environment": env_name,
        "secret_values_returned": False,
    }


def _check(name: str, status: str, detail: str, required: bool = True) -> dict:
    return {"name": name, "status": status, "required": required, "detail": detail}


def _owner_state(auth_store: dict, username: str, policy: dict) -> dict:
    users = auth_store.get("users") if isinstance(auth_store, dict) and isinstance(auth_store.get("users"), dict) else {}
    user = users.get(username) if isinstance(users.get(username), dict) else {}
    role = str(user.get("role") or user.get("user_role") or "user")
    return {
        "role": role,
        "is_required_owner": role == policy["required_owner_role"] or username == "ahmet",
        "owner_confirmed": _safe_bool(user.get("owner_confirmed") or user.get("live_config_owner_confirmed"), False),
        "read_permission": _safe_bool(user.get("read_permission") or user.get("can_read"), bool(user)),
        "trade_permission": _safe_bool(user.get("trade_permission") or user.get("can_trade"), False),
    }


def _governance_checks(source: dict, policy: dict, env: dict, owner: dict) -> dict[str, list[dict]]:
    env_flags = env.get("flags") if isinstance(env.get("flags"), dict) else {}
    command = source.get("command_preview") if isinstance(source.get("command_preview"), dict) else {}
    safety = source.get("safety_contract") if isinstance(source.get("safety_contract"), dict) else {}
    return {
        "source_contract": [
            _check("source_revision_100", "ok" if source.get("revision") == policy["required_source_revision"] else "blocked", "Rev101 must be fed by Rev100 production candidate."),
            _check("source_not_blocked", "ok" if source.get("status") != "blocked" else "blocked", f"Rev100 source status: {source.get('status', 'unknown')}"),
            _check("source_go_no_go_present", "ok" if source.get("go_no_go") in {"GO_CANDIDATE", "REVIEW_READY", "NO_GO"} else "review", "Rev100 go/no-go decision must be visible."),
        ],
        "live_flag_governance": [
            _check("network_calls_disabled", "ok" if not policy["allow_network_calls"] and env_flags.get("HMTSTC_EXCHANGE_NETWORK_ENABLED") is False and command.get("sends_exchange_request") is False else "blocked", "Exchange network calls remain disabled in Rev101 governance."),
            _check("direct_orders_disabled", "ok" if not policy["allow_direct_orders"] and env_flags.get("HMTSTC_DIRECT_ORDER_ENABLED") is False and command.get("places_order") is False else "blocked", "Direct order placement remains disabled."),
            _check("real_submit_disabled", "ok" if not policy["allow_real_submit"] and env_flags.get("HMTSTC_REAL_SUBMIT_ENABLED") is False and command.get("real_submit_enabled") is False else "blocked", "Real submit remains disabled until the later submitter revision."),
            _check("runtime_write_disabled", "ok" if not policy["allow_runtime_write"] and env_flags.get("HMTSTC_RUNTIME_WRITE_ENABLED") is False and command.get("writes_runtime_state") is False else "blocked", "Runtime writes remain disabled in config governance."),
            _check("micro_real_flag_review_only", "ok" if env_flags.get("HMTSTC_MICRO_REAL_ENABLED") is False else "review", "Micro-real enable flag is not consumed for submit in Rev101."),
        ],
        "owner_control": [
            _check("owner_confirmation_required", "ok" if policy["owner_confirmation_required"] and env_flags.get("HMTSTC_OWNER_CONFIRMATION_REQUIRED") is True else "blocked", "Owner confirmation must remain required."),
            _check("owner_role_visible", "ok" if owner["is_required_owner"] else "review", f"Required role: {policy['required_owner_role']}, visible role: {owner['role']}"),
            _check("owner_confirmation_not_auto_applied", "ok" if not owner["owner_confirmed"] or policy["owner_confirmation_required"] else "blocked", "Owner confirmation is evidence only; it cannot auto-enable submit."),
        ],
        "risk_limits": [
            _check("micro_notional_capped", "ok" if 1.0 <= policy["max_micro_notional_usdt"] <= 25.0 else "blocked", f"Micro notional cap: {policy['max_micro_notional_usdt']} USDT."),
            _check("daily_loss_negative", "ok" if policy["max_daily_loss_usdt"] < 0 else "blocked", f"Daily loss cap: {policy['max_daily_loss_usdt']} USDT."),
        ],
        "secret_hygiene": [
            _check("env_snapshot_secret_free", "ok" if env.get("secret_values_returned") is False else "blocked", "Config snapshot returns only flag booleans and hashed version metadata."),
            _check("safety_contract_secret_free", "ok" if safety.get("contains_secret") is False else "blocked", "Upstream safety contract must not expose secrets."),
        ],
    }


def _flatten(checks: dict[str, list[dict]]) -> list[dict]:
    rows: list[dict] = []
    for section, items in checks.items():
        for item in items:
            row = dict(item)
            row["section"] = section
            rows.append(row)
    return rows


def build_autonomous_live_config_governance(data: dict | None, settings: dict | None = None, auth_store: dict | None = None, username: str = "default") -> dict:
    """Rev101 live config governance.

    Read-only configuration governance layer for the first live-control phase.
    It validates runtime flags, owner confirmation requirements, safe caps and
    secret-free config snapshots. It never submits orders, never calls an
    exchange and never writes runtime state.
    """
    data = deepcopy(data or {})
    settings = deepcopy(settings or {})
    auth_store = deepcopy(auth_store or {})
    policy = _policy(settings)
    source = _source(data, settings, auth_store, username)
    env = _safe_env_snapshot()
    owner = _owner_state(auth_store, username, policy)
    checks = _governance_checks(source, policy, env, owner)
    rows = _flatten(checks)
    blockers = [row for row in rows if row.get("required") and row.get("status") == "blocked"]
    reviews = [row for row in rows if row.get("status") == "review"]
    if not policy["enabled"]:
        blockers.append(_check("live_config_governance_disabled", "blocked", "Rev101 live config governance policy is disabled."))
    status = "ok" if not blockers and not reviews else ("blocked" if blockers else "review")
    readiness = "CONFIG_READY_PREVIEW" if status == "ok" else ("CONFIG_BLOCKED" if blockers else "CONFIG_REVIEW")
    evidence_seed = f"rev101|{username}|{source.get('revision')}|{readiness}|{len(blockers)}|{len(reviews)}|{policy['config_version']}"
    return {
        "status": status,
        "revision": 101,
        "engine": "autonomous_live_config_governance",
        "generated_at": now_iso(),
        "source_revision": source.get("revision"),
        "source_status": source.get("status"),
        "readiness": readiness,
        "governance_mode": "read_only_live_config_preview",
        "policy": {
            "expected_environment": policy["expected_environment"],
            "config_version": policy["config_version"],
            "owner_confirmation_required": policy["owner_confirmation_required"],
            "max_micro_notional_usdt": policy["max_micro_notional_usdt"],
            "max_daily_loss_usdt": policy["max_daily_loss_usdt"],
            "allow_network_calls": policy["allow_network_calls"],
            "allow_direct_orders": policy["allow_direct_orders"],
            "allow_real_submit": policy["allow_real_submit"],
            "allow_runtime_write": policy["allow_runtime_write"],
        },
        "safe_runtime_config_snapshot": env,
        "owner_control_state": owner,
        "check_sections": checks,
        "check_totals": {
            "total": len(rows),
            "ok": len([row for row in rows if row.get("status") == "ok"]),
            "review": len(reviews),
            "blocked": len(blockers),
        },
        "blockers": [row.get("name") for row in blockers],
        "warnings": [row.get("name") for row in reviews],
        "command_preview": {
            "type": "live_config_governance_report",
            "read_only": True,
            "places_order": False,
            "sends_exchange_request": False,
            "writes_runtime_state": False,
            "direct_order_enabled": False,
            "real_submit_enabled": False,
            "requires_manual_owner_approval": True,
            "next_allowed_step": "binance_live_permission_verifier" if status != "blocked" else "resolve_config_blockers",
        },
        "safety_contract": {
            "contains_secret": False,
            "direct_order_placement": False,
            "exchange_request": False,
            "runtime_write": False,
            "approval_gated": True,
            "auto_apply": False,
            "manual_go_live_required": True,
        },
        "audit_evidence": {
            "evidence_id": sha256(evidence_seed.encode("utf-8")).hexdigest()[:24],
            "source_engine": source.get("engine"),
            "source_status": source.get("status"),
            "readiness": readiness,
            "blocked_count": len(blockers),
            "review_count": len(reviews),
        },
        "read_only": True,
        "dry_run": True,
    }


def _summary_from_payload(payload: dict) -> dict:
    command = payload.get("command_preview") if isinstance(payload.get("command_preview"), dict) else {}
    return {
        "status": payload.get("status", "review"),
        "revision": 101,
        "engine": "autonomous_live_config_governance_summary",
        "generated_at": payload.get("generated_at"),
        "readiness": payload.get("readiness"),
        "source_revision": payload.get("source_revision"),
        "source_status": payload.get("source_status"),
        "check_totals": payload.get("check_totals") or {},
        "blockers": payload.get("blockers") or [],
        "warnings": payload.get("warnings") or [],
        "policy": payload.get("policy") or {},
        "next_allowed_step": command.get("next_allowed_step"),
        "read_only": True,
        "dry_run": True,
        "direct_order_placement": False,
        "exchange_request": False,
        "runtime_write": False,
        "real_submit_enabled": False,
    }


def build_summary_autonomous_live_config_governance(data: dict | None, settings: dict | None = None, auth_store: dict | None = None, username: str = "default") -> dict:
    return _summary_from_payload(build_autonomous_live_config_governance(data, settings, auth_store, username))


def _sample_data() -> dict:
    source = {
        "status": "ok",
        "revision": 100,
        "engine": "autonomous_production_go_live_candidate",
        "go_no_go": "GO_CANDIDATE",
        "generated_at": "2026-05-24T00:00:00Z",
        "command_preview": {"read_only": True, "places_order": False, "sends_exchange_request": False, "writes_runtime_state": False, "real_submit_enabled": False},
        "safety_contract": {"contains_secret": False, "direct_order_placement": False, "exchange_request": False, "runtime_write": False},
    }
    return {"autonomous_production_go_live_candidate": source}


def build_autonomous_live_config_governance_quality(data: dict | None = None, settings: dict | None = None, auth_store: dict | None = None, username: str = "default") -> dict:
    sample_auth = {"users": {username: {"role": "owner", "read_permission": True, "trade_permission": False, "secret_ref": "masked"}}}
    payload = build_autonomous_live_config_governance(
        data or _sample_data(),
        settings or {"autonomous_live_config_governance": {"enabled": True}},
        auth_store or sample_auth,
        username,
    )
    command = payload.get("command_preview") if isinstance(payload.get("command_preview"), dict) else {}
    snapshot = payload.get("safe_runtime_config_snapshot") if isinstance(payload.get("safe_runtime_config_snapshot"), dict) else {}
    totals = payload.get("check_totals") if isinstance(payload.get("check_totals"), dict) else {}
    checks = {
        "revision_is_101": payload.get("revision") == 101,
        "source_revision_is_100": payload.get("source_revision") == 100,
        "readiness_present": payload.get("readiness") in {"CONFIG_READY_PREVIEW", "CONFIG_REVIEW", "CONFIG_BLOCKED"},
        "config_snapshot_is_secret_free": snapshot.get("secret_values_returned") is False,
        "does_not_place_order": command.get("places_order") is False,
        "does_not_call_exchange": command.get("sends_exchange_request") is False,
        "does_not_write_runtime": command.get("writes_runtime_state") is False,
        "real_submit_off": command.get("real_submit_enabled") is False,
        "direct_order_off": command.get("direct_order_enabled") is False,
        "manual_owner_approval_required": command.get("requires_manual_owner_approval") is True,
        "sample_has_no_blockers": totals.get("blocked", 1) == 0,
        "summary_revision_is_101": _summary_from_payload(payload).get("revision") == 101,
    }
    passed = all(checks.values())
    return {
        "status": "ok" if passed else "review",
        "revision": 101,
        "engine": "autonomous_live_config_governance_quality",
        "generated_at": now_iso(),
        "quality_status": "LIVE_CONFIG_GOVERNANCE_OK" if passed else "LIVE_CONFIG_GOVERNANCE_REVIEW",
        "checks": checks,
        "summary": _summary_from_payload(payload),
        "sample_readiness": payload.get("readiness"),
        "sample_totals": totals,
    }
