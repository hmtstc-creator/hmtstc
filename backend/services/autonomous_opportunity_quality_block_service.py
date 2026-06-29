from __future__ import annotations

from datetime import datetime, timezone
from typing import Any


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _as_dict(value: Any) -> dict:
    return value if isinstance(value, dict) else {}


def _as_list(value: Any) -> list:
    return value if isinstance(value, list) else []


def _safe_float(value: Any, fallback: float = 0.0) -> float:
    try:
        if value is None or value == "":
            return fallback
        return float(value)
    except (TypeError, ValueError):
        return fallback


def _safe_bool(value: Any, fallback: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        text = value.strip().lower()
        if text in {"1", "true", "yes", "on", "enabled", "allow", "allowed", "ready", "ok", "pass"}:
            return True
        if text in {"0", "false", "no", "off", "disabled", "deny", "blocked", "halt", "fail"}:
            return False
    if value is None:
        return fallback
    return bool(value)


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


def _reason(code: str, detail: str, action: str, severity: str = "major", priority: int = 50) -> dict:
    return {"code": code, "severity": severity, "detail": detail, "action": action, "priority": priority}


def _critical(reasons: list[dict]) -> dict:
    if not reasons:
        return {"code": "none", "severity": "ok", "detail": "Opportunity quality is acceptable.", "action": "continue_guarded_preview", "priority": 99}
    weight = {"critical": 0, "major": 1, "minor": 2, "ok": 3}
    return sorted(reasons, key=lambda item: (weight.get(str(item.get("severity")), 2), int(item.get("priority", 50))))[0]


def _command_preview() -> dict:
    return {
        "places_order": False,
        "submits_close_order": False,
        "sends_exchange_request": False,
        "writes_runtime_file": False,
        "journal_write_allowed": True,
        "audit_write_allowed": True,
        "network_default_off": True,
        "real_submit_default_off": True,
        "real_close_default_off": True,
        "auto_execute": False,
        "auto_promote": False,
        "auto_scale": False,
        "auto_apply": False,
    }


def _policy(settings: dict | None) -> dict:
    source: dict[str, Any] = {}
    for key in (
        "autonomous_opportunity_quality",
        "opportunity_quality",
        "autonomous_signal_validator",
        "autonomous_opportunity_router",
        "autonomous_live_strategy_reality_validation",
    ):
        source.update(_settings(settings, key))
    return {
        "min_quality_score": max(0.0, min(1.0, _safe_float(source.get("min_quality_score"), 0.68))),
        "min_route_score": max(0.0, min(1.0, _safe_float(source.get("min_route_score"), 0.62))),
        "min_choch_confidence": max(0.0, min(1.0, _safe_float(source.get("min_choch_confidence"), 0.60))),
        "min_imbalance_confidence": max(0.0, min(1.0, _safe_float(source.get("min_imbalance_confidence"), 0.58))),
        "min_liquidity_score": max(0.0, min(1.0, _safe_float(source.get("min_liquidity_score"), 0.55))),
        "max_spread_bps": max(0.0, _safe_float(source.get("max_spread_bps"), 14.0)),
        "max_fee_slippage_bps": max(0.0, _safe_float(source.get("max_fee_slippage_bps"), 26.0)),
        "max_queue_size": max(1, int(_safe_float(source.get("max_queue_size"), 5))),
        "suppress_low_quality_signals": _safe_bool(source.get("suppress_low_quality_signals"), True),
        "real_submit_enable": _safe_bool(source.get("real_submit_enable"), False),
        "real_close_enable": _safe_bool(source.get("real_close_enable"), False),
        "auto_scale_enable": _safe_bool(source.get("auto_scale_enable"), False),
        "auto_apply_enable": _safe_bool(source.get("auto_apply_enable"), False),
    }


def _raw_opportunities(data: dict | None) -> list[dict]:
    data = data if isinstance(data, dict) else {}
    for key in ("opportunities", "opportunity_queue", "market_opportunities", "signals"):
        items = _as_list(data.get(key))
        if items:
            return [dict(item) for item in items if isinstance(item, dict)]
    nested: list[dict] = []
    for key in ("autonomous_opportunity_router", "opportunity_router", "signal_validator", "market_scanner"):
        node = _as_dict(data.get(key))
        nested = _as_list(node.get("opportunities") or node.get("opportunity_queue") or node.get("signals"))
        if nested:
            return [dict(item) for item in nested if isinstance(item, dict)]
    return [
        {
            "id": "preview-btc-choch-imbalance",
            "symbol": "BTCUSDT",
            "strategy": "choch_imbalance_retest",
            "side": "long",
            "choch_confidence": 0.72,
            "imbalance_confidence": 0.69,
            "liquidity_score": 0.66,
            "regime_score": 0.64,
            "spread_bps": 8.0,
            "fee_slippage_bps": 18.0,
            "risk_score": 0.36,
            "freshness_seconds": 20,
        },
        {
            "id": "preview-eth-low-quality",
            "symbol": "ETHUSDT",
            "strategy": "fast_scalp_breakout",
            "side": "long",
            "choch_confidence": 0.48,
            "imbalance_confidence": 0.42,
            "liquidity_score": 0.57,
            "regime_score": 0.52,
            "spread_bps": 12.0,
            "fee_slippage_bps": 23.0,
            "risk_score": 0.52,
            "freshness_seconds": 35,
        },
    ]


def _score(item: dict, policy: dict) -> dict:
    choch = max(0.0, min(1.0, _safe_float(item.get("choch_confidence"), _safe_float(item.get("structure_score"), 0.50))))
    imbalance = max(0.0, min(1.0, _safe_float(item.get("imbalance_confidence"), _safe_float(item.get("gap_quality"), 0.50))))
    liquidity = max(0.0, min(1.0, _safe_float(item.get("liquidity_score"), 0.50)))
    regime = max(0.0, min(1.0, _safe_float(item.get("regime_score"), _safe_float(item.get("trend_alignment"), 0.50))))
    risk = max(0.0, min(1.0, _safe_float(item.get("risk_score"), 0.50)))
    spread_bps = max(0.0, _safe_float(item.get("spread_bps"), 999.0))
    fee_slippage_bps = max(0.0, _safe_float(item.get("fee_slippage_bps"), _safe_float(item.get("cost_bps"), 999.0)))
    spread_component = max(0.0, 1.0 - (spread_bps / max(1.0, policy["max_spread_bps"] * 2.0)))
    cost_component = max(0.0, 1.0 - (fee_slippage_bps / max(1.0, policy["max_fee_slippage_bps"] * 2.0)))
    quality_score = round(
        (choch * 0.22)
        + (imbalance * 0.22)
        + (liquidity * 0.16)
        + (regime * 0.14)
        + (spread_component * 0.12)
        + (cost_component * 0.10)
        + ((1.0 - risk) * 0.04),
        4,
    )
    route_score = round((quality_score * 0.72) + (liquidity * 0.14) + ((1.0 - risk) * 0.14), 4)
    blockers: list[str] = []
    if choch < policy["min_choch_confidence"]:
        blockers.append("choch_confidence_low")
    if imbalance < policy["min_imbalance_confidence"]:
        blockers.append("imbalance_confidence_low")
    if liquidity < policy["min_liquidity_score"]:
        blockers.append("liquidity_weak")
    if spread_bps > policy["max_spread_bps"]:
        blockers.append("spread_too_wide")
    if fee_slippage_bps > policy["max_fee_slippage_bps"]:
        blockers.append("fee_slippage_cost_high")
    if quality_score < policy["min_quality_score"]:
        blockers.append("quality_score_below_threshold")
    if route_score < policy["min_route_score"]:
        blockers.append("route_score_below_threshold")
    decision = "allow_preview" if not blockers else "suppress" if policy["suppress_low_quality_signals"] else "review"
    return {
        "id": str(item.get("id") or f"{item.get('symbol','UNKNOWN')}-{item.get('strategy','unknown')}").lower(),
        "symbol": str(item.get("symbol") or "UNKNOWN"),
        "strategy": str(item.get("strategy") or "unknown"),
        "side": str(item.get("side") or "n/a"),
        "quality_score": quality_score,
        "route_score": route_score,
        "choch_confidence": choch,
        "imbalance_confidence": imbalance,
        "liquidity_score": liquidity,
        "regime_score": regime,
        "spread_bps": spread_bps,
        "fee_slippage_bps": fee_slippage_bps,
        "risk_score": risk,
        "blockers": blockers,
        "decision": decision,
        "trade_allowed": False,
        "real_submit_close": "OFF",
    }


def _evaluated(data: dict | None, settings: dict | None) -> list[dict]:
    policy = _policy(settings)
    return [_score(item, policy) for item in _raw_opportunities(data)]


def build_rev241_opportunity_quality_score_v2(data: dict | None, settings: dict | None = None, auth_store: dict | None = None, username: str = "default") -> dict:
    policy = _policy(settings)
    scored = _evaluated(data, settings)
    best = sorted(scored, key=lambda item: item["quality_score"], reverse=True)[0] if scored else {}
    checks = [
        _check("opportunity_feed_present", "ok" if scored else "blocked", "Opportunity feed or preview fixture is required.", True, 1, "restore_market_scanner_or_opportunity_router_feed"),
        _check("best_quality_threshold", "ok" if best.get("quality_score", 0) >= policy["min_quality_score"] else "review", "Best opportunity must clear quality threshold before preview.", False, 4, "hold_until_better_micro_opportunity"),
        _check("real_submit_default_off", "ok" if not policy["real_submit_enable"] else "blocked", "Real submit must remain OFF for opportunity quality scoring.", True, 2, "turn_real_submit_off"),
    ]
    return {"engine": "opportunity_quality_score_v2", "revision": 241, "status": _final_status(checks), "generated_at": now_iso(), "opportunity_quality_score_v2": {"best_opportunity": best, "scored_count": len(scored), "min_quality_score": policy["min_quality_score"], "trade_allowed": False, "real_submit_close": "OFF"}, "opportunities": scored, "checks": checks, "check_totals": _totals(checks), "command_preview": _command_preview(), "contains_secret": False, "secret_values_returned": False, "next_allowed_step": "rev242_choch_imbalance_reliability_filter"}


def build_rev242_choch_imbalance_reliability_filter(data: dict | None, settings: dict | None = None, auth_store: dict | None = None, username: str = "default") -> dict:
    policy = _policy(settings)
    scored = _evaluated(data, settings)
    reliable = [i for i in scored if i["choch_confidence"] >= policy["min_choch_confidence"] and i["imbalance_confidence"] >= policy["min_imbalance_confidence"]]
    weak = [i for i in scored if i not in reliable]
    checks = [
        _check("choch_reliability", "ok" if reliable else "review", "At least one CHoCH confirmation should be reliable.", False, 4, "wait_for_confirmed_structure_shift"),
        _check("imbalance_reliability", "ok" if reliable else "review", "At least one imbalance fill/retest setup should be reliable.", False, 5, "wait_for_clean_imbalance_retest"),
        _check("weak_signal_suppression_ready", "ok" if policy["suppress_low_quality_signals"] else "review", "Low-quality signal suppression should stay enabled.", False, 6, "enable_signal_suppression_preview"),
    ]
    return {"engine": "choch_imbalance_reliability_filter", "revision": 242, "status": _final_status(checks), "generated_at": now_iso(), "choch_imbalance_reliability_filter": {"reliable_count": len(reliable), "weak_count": len(weak), "reliable_opportunities": reliable, "weak_opportunities": weak, "trade_allowed": False, "real_submit_close": "OFF"}, "checks": checks, "check_totals": _totals(checks), "command_preview": _command_preview(), "contains_secret": False, "secret_values_returned": False, "next_allowed_step": "rev243_low_quality_signal_suppressor"}


def build_rev243_low_quality_signal_suppressor(data: dict | None, settings: dict | None = None, auth_store: dict | None = None, username: str = "default") -> dict:
    policy = _policy(settings)
    scored = _evaluated(data, settings)
    suppressed = [i for i in scored if i["decision"] == "suppress"]
    retained = [i for i in scored if i["decision"] != "suppress"]
    reasons = []
    if suppressed:
        reasons.append(_reason("low_quality_signals_suppressed", f"{len(suppressed)} weak opportunities suppressed before order preview.", "continue_with_retained_queue_or_hold", "minor", 8))
    if not retained:
        reasons.append(_reason("no_retained_signal", "All opportunities are below the minimum quality standard.", "hold_do_not_trade", "major", 3))
    checks = [
        _check("suppression_enabled", "ok" if policy["suppress_low_quality_signals"] else "review", "Suppression prevents overtrade and fake signal execution.", False, 3, "enable_low_quality_signal_suppression"),
        _check("retained_signal_available", "ok" if retained else "review", "No retained signal means the bot should wait.", False, 5, "hold_until_quality_improves"),
    ]
    critical = _critical(reasons)
    return {"engine": "low_quality_signal_suppressor", "revision": 243, "status": _final_status(checks), "generated_at": now_iso(), "low_quality_signal_suppressor": {"retained_count": len(retained), "suppressed_count": len(suppressed), "suppressed_reasons": reasons, "critical_issue": critical, "retained_opportunities": retained, "suppressed_opportunities": suppressed, "trade_allowed": False, "real_submit_close": "OFF"}, "checks": checks, "check_totals": _totals(checks), "command_preview": _command_preview(), "contains_secret": False, "secret_values_returned": False, "next_allowed_step": "rev244_opportunity_queue_prioritizer"}


def build_rev244_opportunity_queue_prioritizer(data: dict | None, settings: dict | None = None, auth_store: dict | None = None, username: str = "default") -> dict:
    policy = _policy(settings)
    scored = [i for i in _evaluated(data, settings) if i["decision"] != "suppress"]
    queue = sorted(scored, key=lambda item: (item["route_score"], item["quality_score"], -item["spread_bps"]), reverse=True)[: policy["max_queue_size"]]
    best = queue[0] if queue else {}
    checks = [
        _check("queue_not_empty", "ok" if queue else "review", "No qualified opportunity should produce HOLD, not forced trading.", False, 2, "hold_until_queue_has_quality_signal"),
        _check("best_route_threshold", "ok" if best.get("route_score", 0) >= policy["min_route_score"] else "review", "Best routed opportunity must clear route score.", False, 4, "do_not_preview_order_until_route_score_recovers"),
        _check("real_submit_default_off", "ok" if not policy["real_submit_enable"] else "blocked", "Prioritizer never submits real orders.", True, 1, "turn_real_submit_off"),
    ]
    return {"engine": "opportunity_queue_prioritizer", "revision": 244, "status": _final_status(checks), "generated_at": now_iso(), "opportunity_queue_prioritizer": {"queue": queue, "queue_size": len(queue), "best_opportunity": best, "decision": "preview_candidate" if _final_status(checks) == "ok" else "hold", "trade_allowed": False, "real_submit_close": "OFF"}, "checks": checks, "check_totals": _totals(checks), "command_preview": _command_preview(), "contains_secret": False, "secret_values_returned": False, "next_allowed_step": "rev245_autonomous_opportunity_quality_report"}


def build_rev245_autonomous_opportunity_quality_report(data: dict | None, settings: dict | None = None, auth_store: dict | None = None, username: str = "default") -> dict:
    score_payload = build_rev241_opportunity_quality_score_v2(data, settings, auth_store, username)
    filter_payload = build_rev242_choch_imbalance_reliability_filter(data, settings, auth_store, username)
    suppress_payload = build_rev243_low_quality_signal_suppressor(data, settings, auth_store, username)
    queue_payload = build_rev244_opportunity_queue_prioritizer(data, settings, auth_store, username)
    policy = _policy(settings)
    queue = _as_dict(queue_payload.get("opportunity_queue_prioritizer")).get("queue", [])
    best = queue[0] if queue else {}
    reasons: list[dict] = []
    if not queue:
        reasons.append(_reason("no_quality_opportunity", "No opportunity passed quality and reliability filters.", "hold_do_not_trade", "major", 1))
    if best and best.get("quality_score", 0) < policy["min_quality_score"]:
        reasons.append(_reason("best_quality_below_threshold", "Top opportunity is still below required quality threshold.", "wait_for_better_setup", "major", 2))
    if best and best.get("route_score", 0) < policy["min_route_score"]:
        reasons.append(_reason("best_route_score_below_threshold", "Top opportunity route score is below minimum.", "keep_order_preview_blocked", "major", 3))
    if policy["real_submit_enable"] or policy["real_close_enable"]:
        reasons.append(_reason("real_execution_flag_enabled", "Opportunity quality block requires real submit/close to stay OFF.", "turn_real_execution_flags_off", "critical", 0))
    critical = _critical(reasons)
    if critical.get("severity") == "critical":
        decision = "blocked"
    elif queue and not reasons:
        decision = "candidate_ready"
    elif queue:
        decision = "review"
    else:
        decision = "hold"
    report = {
        "decision": decision,
        "opportunity_quality_ready": decision == "candidate_ready",
        "best_opportunity": best,
        "qualified_count": len(queue),
        "suppressed_count": _as_dict(suppress_payload.get("low_quality_signal_suppressor")).get("suppressed_count", 0),
        "critical_issue": critical,
        "operator_action": critical.get("action"),
        "next_action": "order_preview_only" if decision == "candidate_ready" else critical.get("action"),
        "trade_allowed": False,
        "real_submit_close": "OFF",
        "auto_scale": "OFF",
        "auto_apply": "OFF",
    }
    checks = []
    for payload in (score_payload, filter_payload, suppress_payload, queue_payload):
        checks.extend(_as_list(payload.get("checks")))
    status = "blocked" if critical.get("severity") == "critical" else "ok" if decision == "candidate_ready" else "review"
    return {"engine": "autonomous_opportunity_quality_report", "revision": 245, "status": status, "generated_at": now_iso(), "autonomous_opportunity_quality_report": report, "quality_score_v2": score_payload.get("opportunity_quality_score_v2"), "choch_imbalance_filter": filter_payload.get("choch_imbalance_reliability_filter"), "low_quality_signal_suppressor": suppress_payload.get("low_quality_signal_suppressor"), "opportunity_queue_prioritizer": queue_payload.get("opportunity_queue_prioritizer"), "checks": checks, "check_totals": _totals(checks), "summary_result": build_summary_for_revision(245, data, settings, auth_store, username), "command_preview": _command_preview(), "contains_secret": False, "secret_values_returned": False, "next_allowed_step": "rev246_limited_live_operator_approval_ux"}


def build_for_revision(revision: int, data: dict | None, settings: dict | None = None, auth_store: dict | None = None, username: str = "default") -> dict:
    builders = {
        241: build_rev241_opportunity_quality_score_v2,
        242: build_rev242_choch_imbalance_reliability_filter,
        243: build_rev243_low_quality_signal_suppressor,
        244: build_rev244_opportunity_queue_prioritizer,
        245: build_rev245_autonomous_opportunity_quality_report,
    }
    if int(revision) not in builders:
        raise ValueError(f"Unsupported Rev241-245 opportunity quality revision: {revision}")
    return builders[int(revision)](data, settings, auth_store, username)


def build_block_payload(data: dict | None, settings: dict | None = None, auth_store: dict | None = None, username: str = "default") -> dict:
    rev241 = build_rev241_opportunity_quality_score_v2(data, settings, auth_store, username)
    rev242 = build_rev242_choch_imbalance_reliability_filter(data, settings, auth_store, username)
    rev243 = build_rev243_low_quality_signal_suppressor(data, settings, auth_store, username)
    rev244 = build_rev244_opportunity_queue_prioritizer(data, settings, auth_store, username)
    rev245 = build_rev245_autonomous_opportunity_quality_report(data, settings, auth_store, username)
    checks: list[dict] = []
    for payload in (rev241, rev242, rev243, rev244, rev245):
        checks.extend(_as_list(payload.get("checks")))
    report = rev245.get("autonomous_opportunity_quality_report", {})
    return {
        "engine": "autonomous_opportunity_quality_block",
        "revision": 245,
        "status": rev245.get("status", "review"),
        "generated_at": now_iso(),
        "rev241_opportunity_quality_score_v2": rev241,
        "rev242_choch_imbalance_reliability_filter": rev242,
        "rev243_low_quality_signal_suppressor": rev243,
        "rev244_opportunity_queue_prioritizer": rev244,
        "rev245_autonomous_opportunity_quality_report": rev245,
        "autonomous_opportunity_quality_report": report,
        "summary_result": build_summary_for_revision(245, data, settings, auth_store, username),
        "checks": checks,
        "check_totals": _totals(checks),
        "command_preview": _command_preview(),
        "contains_secret": False,
        "secret_values_returned": False,
        "next_allowed_step": "rev246_limited_live_operator_approval_ux",
    }


def build_summary_for_revision(revision: int, data: dict | None, settings: dict | None = None, auth_store: dict | None = None, username: str = "default") -> dict:
    payload = build_for_revision(revision, data, settings, auth_store, username) if int(revision) != 245 else None
    if int(revision) == 245:
        policy = _policy(settings)
        queue_payload = build_rev244_opportunity_queue_prioritizer(data, settings, auth_store, username)
        suppress_payload = build_rev243_low_quality_signal_suppressor(data, settings, auth_store, username)
        queue = _as_dict(queue_payload.get("opportunity_queue_prioritizer")).get("queue", [])
        best = queue[0] if queue else {}
        reasons = []
        if not queue:
            reasons.append(_reason("no_quality_opportunity", "No opportunity passed filters.", "hold_do_not_trade", "major", 1))
        if policy["real_submit_enable"] or policy["real_close_enable"]:
            reasons.append(_reason("real_execution_flag_enabled", "Real execution flags must stay OFF.", "turn_real_execution_flags_off", "critical", 0))
        critical = _critical(reasons)
        decision = "candidate_ready" if queue and critical.get("severity") == "ok" else "blocked" if critical.get("severity") == "critical" else "hold"
        return {
            "revision": 245,
            "decision": decision,
            "opportunity_quality_ready": decision == "candidate_ready",
            "critical_issue": critical.get("code"),
            "operator_action": critical.get("action"),
            "best_symbol": best.get("symbol"),
            "best_strategy": best.get("strategy"),
            "best_quality_score": best.get("quality_score", 0),
            "qualified_count": len(queue),
            "suppressed_count": _as_dict(suppress_payload.get("low_quality_signal_suppressor")).get("suppressed_count", 0),
            "trade_allowed": False,
            "real_submit_close": "OFF",
            "auto_apply": "OFF",
        }
    body_key = {
        241: "opportunity_quality_score_v2",
        242: "choch_imbalance_reliability_filter",
        243: "low_quality_signal_suppressor",
        244: "opportunity_queue_prioritizer",
    }.get(int(revision), "summary")
    body = _as_dict(payload.get(body_key)) if payload else {}
    return {"revision": int(revision), "decision": body.get("decision") or payload.get("status", "review"), "critical_issue": (_critical([c for c in _as_list(payload.get("checks")) if c.get("status") != "ok"]).get("code") if payload else "review"), "trade_allowed": False, "real_submit_close": "OFF"}


def build_quality_for_revision(revision: int, data: dict | None, settings: dict | None = None, auth_store: dict | None = None, username: str = "default") -> dict:
    payload = build_for_revision(revision, data, settings, auth_store, username)
    command = payload.get("command_preview", {})
    failures = []
    if command.get("places_order") or command.get("sends_exchange_request") or command.get("submits_close_order"):
        failures.append("unexpected_execution_side_effect")
    if command.get("real_submit_default_off") is not True or command.get("real_close_default_off") is not True:
        failures.append("real_execution_not_default_off")
    if payload.get("contains_secret") or payload.get("secret_values_returned"):
        failures.append("secret_leak")
    if command.get("auto_scale") or command.get("auto_apply"):
        failures.append("auto_scale_or_apply_enabled")
    return {"quality_gate": "FAIL" if failures else "PASS", "revision": int(revision), "engine": payload.get("engine"), "status": payload.get("status"), "failures": failures, "command_preview": command, "checked_at": now_iso()}
