from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
from typing import Any


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _safe_bool(value: Any, fallback: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        text = value.strip().lower()
        if text in {"1", "true", "yes", "on", "enabled", "allow", "allowed", "ready", "confirmed", "ok", "pass"}:
            return True
        if text in {"0", "false", "no", "off", "disabled", "deny", "blocked", "halt", "emergency", "fail"}:
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


def _safe_int(value: Any, fallback: int = 0) -> int:
    try:
        if value is None or value == "":
            return fallback
        return int(float(value))
    except (TypeError, ValueError):
        return fallback


def _as_dict(value: Any) -> dict:
    return value if isinstance(value, dict) else {}


def _as_list(value: Any) -> list:
    return value if isinstance(value, list) else []


def _settings(settings: dict | None, key: str) -> dict:
    settings = settings if isinstance(settings, dict) else {}
    return _as_dict(settings.get(key))


def _check(name: str, status: str, detail: str, required: bool = True, priority: int = 50, action: str = "review") -> dict:
    return {"name": name, "status": status, "required": required, "priority": priority, "detail": detail, "action": action}


def _totals(checks: list[dict]) -> dict:
    return {
        "total": len(checks),
        "ok": len([c for c in checks if c.get("status") == "ok"]),
        "review": len([c for c in checks if c.get("status") == "review"]),
        "blocked": len([c for c in checks if c.get("status") == "blocked"]),
    }


def _final_status(checks: list[dict]) -> str:
    required = [c for c in checks if c.get("required", True)]
    if any(c.get("status") == "blocked" for c in required):
        return "blocked"
    if any(c.get("status") == "review" for c in checks):
        return "review"
    return "ok"


def _command_preview() -> dict:
    return {
        "places_order": False,
        "submits_close_order": False,
        "sends_exchange_request": False,
        "writes_runtime_file": False,
        "network_default_off": True,
        "real_submit_default_off": True,
        "real_close_default_off": True,
        "owner_approval_required": True,
        "approval_gated": True,
        "auto_execute": False,
        "auto_promote": False,
        "auto_scale": False,
        "auto_apply": False,
    }


def _policy(settings: dict | None) -> dict:
    source: dict[str, Any] = {}
    for key in (
        "autonomous_limited_live_activation_rehearsal",
        "autonomous_real_execution_reconciliation",
        "autonomous_live_risk_firewall",
        "autonomous_first_controlled_micro_live",
    ):
        source.update(_settings(settings, key))
    return {
        "real_network_enable": _safe_bool(source.get("real_network_enable"), False),
        "real_submit_enable": _safe_bool(source.get("real_submit_enable"), False),
        "real_close_enable": _safe_bool(source.get("real_close_enable"), False),
        "auto_scale_enable": _safe_bool(source.get("auto_scale_enable"), False),
        "auto_apply_enable": _safe_bool(source.get("auto_apply_enable"), False),
        "owner_approval_required": _safe_bool(source.get("owner_approval_required"), True),
        "activation_token_required": _safe_bool(source.get("activation_token_required"), True),
        "exchange_permission_required": _safe_bool(source.get("exchange_permission_required"), True),
        "max_notional_usdt": max(0.0, _safe_float(source.get("max_notional_usdt"), 10.0)),
        "max_loss_usdt": max(0.0, _safe_float(source.get("max_loss_usdt"), 1.5)),
        "max_daily_loss_usdt": max(0.0, _safe_float(source.get("max_daily_loss_usdt"), 5.0)),
        "session_minutes": max(1, _safe_int(source.get("session_minutes"), 30)),
        "timeout_seconds": max(30, _safe_int(source.get("timeout_seconds"), 900)),
        "allowed_symbols": [str(x).upper().strip() for x in source.get("allowed_symbols", ["BTCUSDT", "ETHUSDT"]) if str(x).strip()],
        "allowed_strategies": [str(x).strip() for x in source.get("allowed_strategies", ["choch_imbalance_micro", "scalp_reversion_guarded"]) if str(x).strip()],
        "default_symbol": str(source.get("default_symbol") or "BTCUSDT").upper().strip(),
        "default_strategy": str(source.get("default_strategy") or "choch_imbalance_micro").strip(),
        "target_profit_ratio": max(0.0, _safe_float(source.get("target_profit_ratio"), 0.006)),
        "stop_loss_ratio": max(0.0, _safe_float(source.get("stop_loss_ratio"), 0.004)),
        "trailing_enabled_preview": _safe_bool(source.get("trailing_enabled_preview"), True),
    }


def _auth_flags(auth_store: dict | None, username: str) -> dict:
    auth_store = auth_store if isinstance(auth_store, dict) else {}
    candidates = [auth_store]
    users = auth_store.get("users") if isinstance(auth_store.get("users"), dict) else {}
    if isinstance(users.get(username), dict):
        candidates.append(users[username])
    if isinstance(auth_store.get(username), dict):
        candidates.append(auth_store[username])
    merged: dict[str, Any] = {}
    for item in candidates:
        merged.update(item)
    # Never return tokens/secrets; only derived booleans.
    return {
        "owner_approved": _safe_bool(merged.get("owner_approved") or merged.get("approval_confirmed"), False),
        "activation_token_present": bool(merged.get("activation_token") or merged.get("activation_token_preview") or merged.get("token_preview")),
        "api_key_present": bool(merged.get("api_key") or merged.get("binance_api_key")),
        "api_secret_present": bool(merged.get("api_secret") or merged.get("binance_api_secret")),
        "trade_permission": _safe_bool(merged.get("trade_permission") or merged.get("binance_trade_permission"), False),
        "withdraw_permission": _safe_bool(merged.get("withdraw_permission"), False),
    }


def _candidate(data: dict | None, settings: dict | None) -> dict:
    data = data if isinstance(data, dict) else {}
    policy = _policy(settings)
    src = _as_dict(data.get("first_micro_live_intent")) or _as_dict(data.get("candidate_trade")) or _as_dict(data.get("opportunity")) or {}
    symbol = str(src.get("symbol") or data.get("symbol") or policy["default_symbol"]).upper().strip()
    strategy = str(src.get("strategy") or src.get("strategy_id") or data.get("strategy") or policy["default_strategy"]).strip()
    notional = min(max(0.0, _safe_float(src.get("notional_usdt") or src.get("size_usdt"), policy["max_notional_usdt"])), policy["max_notional_usdt"])
    max_loss = min(max(0.0, _safe_float(src.get("max_loss_usdt"), policy["max_loss_usdt"])), policy["max_loss_usdt"])
    return {
        "symbol": symbol,
        "strategy": strategy,
        "regime": str(src.get("regime") or _as_dict(data.get("market")).get("regime") or data.get("regime") or "unknown"),
        "size_usdt": round(notional, 6),
        "max_loss_usdt": round(max_loss, 6),
        "tp_ratio": _safe_float(src.get("tp_ratio"), policy["target_profit_ratio"]),
        "sl_ratio": _safe_float(src.get("sl_ratio"), policy["stop_loss_ratio"]),
        "timeout_seconds": _safe_int(src.get("timeout_seconds"), policy["timeout_seconds"]),
    }


def _latest_block(data: dict | None, *keys: str) -> dict:
    data = data if isinstance(data, dict) else {}
    for key in keys:
        value = data.get(key)
        if isinstance(value, dict):
            return value
    outputs = _as_dict(data.get("outputs"))
    for key in keys:
        value = outputs.get(key)
        if isinstance(value, dict):
            return value
    return {}


def _owner_action() -> str:
    return "review_preview_and_confirm_owner_approval_only_if_real_micro_live_is_intended"


def _major_reason(code: str, detail: str, action: str, severity: str = "major", priority: int = 50) -> dict:
    return {"code": code, "severity": severity, "detail": detail, "action": action, "priority": priority}


def _critical(reasons: list[dict]) -> dict:
    if not reasons:
        return {"code": "none", "severity": "ok", "detail": "No blocker detected.", "action": "continue_preview"}
    weight = {"critical": 0, "major": 1, "minor": 2, "ok": 3}
    return sorted(reasons, key=lambda x: (weight.get(str(x.get("severity")), 2), int(x.get("priority", 50))))[0]


def build_rev196_first_micro_live_intent_contract(data: dict | None, settings: dict | None = None, auth_store: dict | None = None, username: str = "default") -> dict:
    data, settings = deepcopy(data or {}), deepcopy(settings or {})
    policy = _policy(settings)
    candidate = _candidate(data, settings)
    checks = [
        _check("symbol_whitelisted", "ok" if candidate["symbol"] in policy["allowed_symbols"] else "blocked", "Symbol must be inside micro-live whitelist.", True, 1, "block_symbol"),
        _check("strategy_allowed", "ok" if candidate["strategy"] in policy["allowed_strategies"] else "blocked", "Strategy must be allowed for first micro-live.", True, 2, "block_strategy"),
        _check("size_within_max_notional", "ok" if 0 < candidate["size_usdt"] <= policy["max_notional_usdt"] else "blocked", "Intent size must stay inside max notional.", True, 3, "reduce_size"),
        _check("max_loss_within_policy", "ok" if 0 < candidate["max_loss_usdt"] <= policy["max_loss_usdt"] else "blocked", "Intent max loss must stay inside policy.", True, 4, "reduce_max_loss"),
        _check("secret_free_contract", "ok", "Contract contains no API key, secret, token or credential values."),
    ]
    contract = {
        "contract_id_preview": f"micro-live-intent-{candidate['symbol']}-{candidate['strategy']}",
        "symbol": candidate["symbol"],
        "strategy": candidate["strategy"],
        "regime": candidate["regime"],
        "size_usdt": candidate["size_usdt"],
        "max_loss_usdt": candidate["max_loss_usdt"],
        "tp_ratio": candidate["tp_ratio"],
        "sl_ratio": candidate["sl_ratio"],
        "timeout_seconds": candidate["timeout_seconds"],
        "entry_condition": "validated_opportunity_and_live_risk_firewall_trade_allowed",
        "exit_condition": "tp_sl_trailing_time_stop_or_manual_attention",
        "owner_approval_scope": "first_controlled_micro_live_only",
        "secret_free": True,
    }
    return {"engine": "first_micro_live_intent_contract", "revision": 196, "status": _final_status(checks), "generated_at": now_iso(), "intent_contract": contract, "checks": checks, "check_totals": _totals(checks), "command_preview": _command_preview(), "contains_secret": False, "secret_values_returned": False, "next_allowed_step": "rev197_approval_gated_submit_path_hardening"}


def build_rev197_approval_gated_submit_path_hardening(data: dict | None, settings: dict | None = None, auth_store: dict | None = None, username: str = "default") -> dict:
    data, settings = deepcopy(data or {}), deepcopy(settings or {})
    policy = _policy(settings)
    auth = _auth_flags(auth_store, username)
    risk_block = _latest_block(data, "autonomous_live_risk_firewall_block", "live_risk_firewall_packet")
    risk_packet = _as_dict(risk_block.get("live_risk_firewall_packet")) or risk_block
    risk_allows = str(risk_packet.get("decision") or risk_packet.get("trade_permission") or "blocked").lower() in {"trade_allowed", "allowed", "limited-go", "go"}
    submit_gate_reasons: list[dict] = []
    if not policy["real_network_enable"]:
        submit_gate_reasons.append(_major_reason("real_network_default_off", "Real exchange network flag is OFF by default.", "keep_submit_blocked", "critical", 1))
    if not policy["real_submit_enable"]:
        submit_gate_reasons.append(_major_reason("real_submit_default_off", "Real submit flag is OFF by default.", "keep_submit_blocked", "critical", 2))
    if policy["owner_approval_required"] and not auth["owner_approved"]:
        submit_gate_reasons.append(_major_reason("owner_approval_missing", "Owner approval is required before any live action.", "request_owner_review", "critical", 3))
    if policy["activation_token_required"] and not auth["activation_token_present"]:
        submit_gate_reasons.append(_major_reason("activation_token_missing", "Activation token preview/confirmation is required.", "generate_preview_then_owner_confirm", "critical", 4))
    if policy["exchange_permission_required"] and not auth["trade_permission"]:
        submit_gate_reasons.append(_major_reason("exchange_trade_permission_missing", "Exchange trade permission is not confirmed.", "keep_submit_blocked", "critical", 5))
    if auth["withdraw_permission"]:
        submit_gate_reasons.append(_major_reason("withdraw_permission_detected", "Withdraw permission must not be present for trading key.", "rotate_key_without_withdraw", "critical", 6))
    if not risk_allows:
        submit_gate_reasons.append(_major_reason("risk_firewall_not_allowing", "Live risk firewall does not explicitly allow trade.", "hold", "major", 10))
    allowed = len(submit_gate_reasons) == 0
    checks = [
        _check("default_submit_blocked", "ok" if not policy["real_network_enable"] and not policy["real_submit_enable"] else "blocked", "Default path proves submit is blocked unless explicit flags are enabled."),
        _check("owner_approval_gate", "ok" if not allowed or auth["owner_approved"] else "blocked", "Owner approval is mandatory for live submit."),
        _check("token_permission_risk_gates", "ok" if not allowed or (auth["activation_token_present"] and auth["trade_permission"] and risk_allows) else "blocked", "Token, exchange permission and risk firewall are chained."),
        _check("no_real_network_side_effect", "ok", "This service never sends network requests or orders."),
    ]
    return {"engine": "approval_gated_submit_path_hardening", "revision": 197, "status": _final_status(checks), "generated_at": now_iso(), "submit_path": {"submit_allowed": allowed, "default_blocked": not policy["real_submit_enable"], "approval_gated": True, "reasons": submit_gate_reasons, "critical_reason": _critical(submit_gate_reasons), "required_gates": ["explicit_enable", "owner_approval", "activation_token", "exchange_trade_permission", "risk_firewall", "whitelist", "session_boundary"], "real_submit": "OFF" if not policy["real_submit_enable"] else "APPROVAL_GATED"}, "checks": checks, "check_totals": _totals(checks), "command_preview": _command_preview(), "contains_secret": False, "secret_values_returned": False, "next_allowed_step": "rev198_micro_live_exit_plan_contract"}


def build_rev198_micro_live_exit_plan_contract(data: dict | None, settings: dict | None = None, auth_store: dict | None = None, username: str = "default") -> dict:
    intent = build_rev196_first_micro_live_intent_contract(data, settings, auth_store, username).get("intent_contract", {})
    policy = _policy(settings)
    checks = [
        _check("exit_plan_predefined", "ok", "TP, SL, trailing, time stop, manual attention and emergency conditions are predefined."),
        _check("auto_close_default_off", "ok" if not policy["real_close_enable"] else "blocked", "Auto-close / direct close remains default OFF."),
        _check("manual_attention_on_exit_uncertainty", "ok", "Exit uncertainty routes to attention instead of blind action."),
    ]
    exit_plan = {
        "symbol": intent.get("symbol"),
        "strategy": intent.get("strategy"),
        "tp_ratio": intent.get("tp_ratio"),
        "sl_ratio": intent.get("sl_ratio"),
        "max_loss_usdt": intent.get("max_loss_usdt"),
        "trailing_preview": "enabled" if policy["trailing_enabled_preview"] else "disabled",
        "time_stop_seconds": intent.get("timeout_seconds"),
        "manual_attention_condition": ["partial_fill_unresolved", "reconciliation_inconsistent", "exchange_status_unknown", "latency_or_slippage_outlier"],
        "emergency_condition": ["daily_hard_stop_reached", "max_loss_breached", "exchange_or_position_state_unknown"],
        "auto_close": "OFF" if not policy["real_close_enable"] else "APPROVAL_GATED",
        "approval_gated_close_required": True,
        "secret_free": True,
    }
    return {"engine": "micro_live_exit_plan_contract", "revision": 198, "status": _final_status(checks), "generated_at": now_iso(), "exit_plan_contract": exit_plan, "checks": checks, "check_totals": _totals(checks), "command_preview": _command_preview(), "contains_secret": False, "secret_values_returned": False, "next_allowed_step": "rev199_micro_live_result_capture"}


def build_rev199_micro_live_result_capture(data: dict | None, settings: dict | None = None, auth_store: dict | None = None, username: str = "default") -> dict:
    data = deepcopy(data or {})
    result = _as_dict(data.get("micro_live_result")) or _as_dict(data.get("last_micro_live_result"))
    fields = ["pnl_usdt", "fee_usdt", "slippage_bps", "latency_ms", "fill_quality", "exit_reason", "risk_event", "strategy_result", "journal_consistency"]
    missing = [f for f in fields if f not in result]
    checks = [
        _check("result_schema_defined", "ok", "PnL, fee, slippage, latency, fill quality, exit reason, risk event, strategy result and journal consistency fields are defined."),
        _check("runtime_secret_free", "ok", "Result capture schema has no credential fields."),
        _check("actual_result_available", "review" if missing else "ok", "Actual micro-live result is not expected before first controlled live trade.", False, 50, "capture_after_trade"),
    ]
    capture_schema = {
        "required_fields": fields,
        "missing_fields_in_current_runtime": missing,
        "sample_size": 1 if result else 0,
        "latest_result_preview": {k: result.get(k) for k in fields if k in result},
        "journal_write_allowed": True,
        "runtime_secret_allowed": False,
        "network_side_effect": False,
    }
    return {"engine": "micro_live_result_capture", "revision": 199, "status": _final_status(checks), "generated_at": now_iso(), "result_capture": capture_schema, "checks": checks, "check_totals": _totals(checks), "command_preview": _command_preview(), "contains_secret": False, "secret_values_returned": False, "next_allowed_step": "rev200_first_controlled_micro_live_go_no_go"}


def build_rev200_first_controlled_micro_live_go_no_go(data: dict | None, settings: dict | None = None, auth_store: dict | None = None, username: str = "default") -> dict:
    data, settings = deepcopy(data or {}), deepcopy(settings or {})
    intent = build_rev196_first_micro_live_intent_contract(data, settings, auth_store, username)
    submit = build_rev197_approval_gated_submit_path_hardening(data, settings, auth_store, username)
    exit_plan = build_rev198_micro_live_exit_plan_contract(data, settings, auth_store, username)
    capture = build_rev199_micro_live_result_capture(data, settings, auth_store, username)
    policy = _policy(settings)
    blockers: list[dict] = []
    for payload in (intent, submit, exit_plan):
        for check in payload.get("checks", []):
            if check.get("status") == "blocked":
                blockers.append(_major_reason(check.get("name", "blocked"), check.get("detail", "Blocked."), check.get("action", "review"), "critical", check.get("priority", 50)))
    submit_body = _as_dict(submit.get("submit_path"))
    blockers.extend(submit_body.get("reasons") or [])
    critical = _critical(blockers)
    # LIMITED-GO is possible only after explicit flags and approvals. Default package should safely land on NO-GO.
    if blockers:
        decision = "NO-GO"
    elif policy["real_network_enable"] and policy["real_submit_enable"]:
        decision = "LIMITED-GO"
    else:
        decision = "NO-GO"
    contract = intent.get("intent_contract", {})
    packet = {
        "decision": decision,
        "symbol": contract.get("symbol"),
        "strategy": contract.get("strategy"),
        "max_notional_usdt": contract.get("size_usdt"),
        "session_minutes": policy["session_minutes"],
        "max_loss_usdt": contract.get("max_loss_usdt"),
        "emergency_condition": _as_dict(exit_plan.get("exit_plan_contract")).get("emergency_condition", []),
        "owner_action": _owner_action() if decision != "GO" else "monitor_session_boundary_and_reconciliation",
        "critical_blocker": critical,
        "submit_path": submit_body.get("real_submit", "OFF"),
        "real_network": "OFF" if not policy["real_network_enable"] else "APPROVAL_GATED",
        "real_close": "OFF" if not policy["real_close_enable"] else "APPROVAL_GATED",
        "auto_scale": "OFF",
        "auto_apply": "OFF",
        "summary_visible": {
            "go_no_go": decision,
            "symbol": contract.get("symbol"),
            "max_notional_usdt": contract.get("size_usdt"),
            "session_minutes": policy["session_minutes"],
            "max_loss_usdt": contract.get("max_loss_usdt"),
            "blocker": critical.get("code"),
            "owner_action": _owner_action(),
        },
    }
    checks = [
        _check("intent_contract_ready", intent.get("status", "blocked"), "Intent contract must be valid."),
        _check("submit_path_hardened", "ok" if submit_body.get("default_blocked") else "blocked", "Default submit must remain blocked."),
        _check("exit_plan_ready", exit_plan.get("status", "blocked"), "Exit plan must be predefined."),
        _check("result_capture_schema_ready", "ok" if capture.get("result_capture") else "blocked", "Result capture schema must exist."),
        _check("real_submit_close_default_off", "ok" if not policy["real_submit_enable"] and not policy["real_close_enable"] else "blocked", "Submit/close remain OFF unless explicitly approval-gated."),
    ]
    return {"engine": "first_controlled_micro_live_go_no_go", "revision": 200, "status": _final_status(checks), "generated_at": now_iso(), "first_controlled_micro_live_packet": packet, "checks": checks, "check_totals": _totals(checks), "command_preview": _command_preview(), "contains_secret": False, "secret_values_returned": False, "next_allowed_step": "rev201_post_first_trade_learning_freeze_block"}


_REVISION_BUILDERS = {
    196: build_rev196_first_micro_live_intent_contract,
    197: build_rev197_approval_gated_submit_path_hardening,
    198: build_rev198_micro_live_exit_plan_contract,
    199: build_rev199_micro_live_result_capture,
    200: build_rev200_first_controlled_micro_live_go_no_go,
}


def build_for_revision(revision: int, data: dict | None, settings: dict | None = None, auth_store: dict | None = None, username: str = "default") -> dict:
    revision = int(revision)
    if revision not in _REVISION_BUILDERS:
        raise ValueError(f"Unsupported Rev196-200 revision: {revision}")
    return _REVISION_BUILDERS[revision](data, settings, auth_store, username)


def build_block_payload(data: dict | None, settings: dict | None = None, auth_store: dict | None = None, username: str = "default") -> dict:
    outputs = {
        "autonomous_first_micro_live_intent_contract": build_rev196_first_micro_live_intent_contract(data, settings, auth_store, username),
        "autonomous_approval_gated_submit_path_hardening": build_rev197_approval_gated_submit_path_hardening(data, settings, auth_store, username),
        "autonomous_micro_live_exit_plan_contract": build_rev198_micro_live_exit_plan_contract(data, settings, auth_store, username),
        "autonomous_micro_live_result_capture": build_rev199_micro_live_result_capture(data, settings, auth_store, username),
        "autonomous_first_controlled_micro_live_go_no_go": build_rev200_first_controlled_micro_live_go_no_go(data, settings, auth_store, username),
    }
    final = outputs["autonomous_first_controlled_micro_live_go_no_go"]
    block_status = "blocked" if any(x.get("status") == "blocked" for x in outputs.values()) else "review" if any(x.get("status") == "review" for x in outputs.values()) else "ok"
    return {"engine": "autonomous_first_controlled_micro_live_block", "revision": 200, "status": block_status, "generated_at": now_iso(), "username": username, "outputs": outputs, "summary_result": final.get("first_controlled_micro_live_packet", {}).get("summary_visible", {}), "first_controlled_micro_live_packet": final.get("first_controlled_micro_live_packet", {}), "auto_apply_default_off": True, "auto_scale_default_off": True, "real_submit_default_off": True, "real_close_default_off": True, "command_preview": _command_preview(), "contains_secret": False, "secret_values_returned": False, "next_allowed_step": "rev201_post_first_trade_learning_freeze_block"}


def build_summary_for_revision(revision: int, data: dict | None, settings: dict | None = None, auth_store: dict | None = None, username: str = "default") -> dict:
    payload = build_for_revision(revision, data, settings, auth_store, username)
    body = payload.get("intent_contract") or payload.get("submit_path") or payload.get("exit_plan_contract") or payload.get("result_capture") or payload.get("first_controlled_micro_live_packet") or {}
    return {"revision": int(revision), "status": payload.get("status"), "decision": body.get("decision") or body.get("submit_allowed") or body.get("symbol"), "critical_issue": (_as_dict(body.get("critical_blocker")) or _as_dict(body.get("critical_reason"))).get("code"), "operator_action": body.get("owner_action") or _owner_action(), "command_preview": payload.get("command_preview"), "contains_secret": False, "secret_values_returned": False}


def build_quality_for_revision(revision: int, data: dict | None, settings: dict | None = None, auth_store: dict | None = None, username: str = "default") -> dict:
    payload = build_for_revision(revision, data, settings, auth_store, username)
    checks = payload.get("checks") or []
    # Rev199 has an intentional non-required review when no real trade result exists; it is still quality-pass for readiness schema.
    status = _final_status([c for c in checks if c.get("required", True)])
    return {"engine": "autonomous_first_controlled_micro_live_quality_gate", "revision": int(revision), "quality_gate": "PASS" if status == "ok" else "FAIL", "status": status, "checks": checks, "check_totals": _totals(checks), "network_default_off": True, "real_submit_default_off": True, "real_close_default_off": True, "auto_scale_default_off": True, "auto_apply_default_off": True, "contains_secret": False, "secret_values_returned": False}
