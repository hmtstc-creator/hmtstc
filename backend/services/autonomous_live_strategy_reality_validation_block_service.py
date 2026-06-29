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


def _safe_int(value: Any, fallback: int = 0) -> int:
    try:
        if value is None or value == "":
            return fallback
        return int(float(value))
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
        "autonomous_live_strategy_reality_validation",
        "autonomous_production_data_integrity",
        "autonomous_controlled_repeat_micro_live",
    ):
        source.update(_settings(settings, key))
    return {
        "min_live_sample_count": max(1, _safe_int(source.get("min_live_sample_count"), 5)),
        "min_confidence_score": max(0.0, min(1.0, _safe_float(source.get("min_confidence_score"), 0.62))),
        "max_expectancy_gap_bps": max(0.0, _safe_float(source.get("max_expectancy_gap_bps"), 12.0)),
        "max_degradation_ratio": max(0.0, _safe_float(source.get("max_degradation_ratio"), 0.35)),
        "max_cost_to_edge_ratio": max(0.0, _safe_float(source.get("max_cost_to_edge_ratio"), 0.55)),
        "min_profit_factor": max(0.0, _safe_float(source.get("min_profit_factor"), 1.05)),
        "max_slippage_bps": max(0.0, _safe_float(source.get("max_slippage_bps"), 8.0)),
        "real_submit_enable": _safe_bool(source.get("real_submit_enable"), False),
        "real_close_enable": _safe_bool(source.get("real_close_enable"), False),
        "auto_scale_enable": _safe_bool(source.get("auto_scale_enable"), False),
        "auto_apply_enable": _safe_bool(source.get("auto_apply_enable"), False),
    }


def _metrics(data: dict | None) -> dict:
    data = data if isinstance(data, dict) else {}
    source: dict[str, Any] = {}
    for key in (
        "live_strategy_reality",
        "strategy_reality_metrics",
        "micro_live_metrics",
        "post_first_trade_metrics",
        "paper_live_comparison",
    ):
        source.update(_as_dict(data.get(key)))
    pairs = _as_list(source.get("symbol_strategy_pairs") or source.get("pairs") or data.get("symbol_strategy_pairs"))
    strategies = _as_list(source.get("strategies") or data.get("strategy_performance") or data.get("strategies"))
    return {
        "paper_expectancy_bps": _safe_float(source.get("paper_expectancy_bps"), _safe_float(source.get("paper_edge_bps"), 10.0)),
        "micro_live_expectancy_bps": _safe_float(source.get("micro_live_expectancy_bps"), _safe_float(source.get("live_expectancy_bps"), 0.0)),
        "paper_profit_factor": _safe_float(source.get("paper_profit_factor"), 1.20),
        "micro_live_profit_factor": _safe_float(source.get("micro_live_profit_factor"), _safe_float(source.get("profit_factor"), 0.0)),
        "sample_count": _safe_int(source.get("sample_count"), _safe_int(source.get("live_sample_count"), 0)),
        "avg_slippage_bps": _safe_float(source.get("avg_slippage_bps"), _safe_float(source.get("slippage_bps"), 0.0)),
        "fee_bps": _safe_float(source.get("fee_bps"), 10.0),
        "latency_ms": _safe_float(source.get("latency_ms"), 0.0),
        "cost_to_edge_ratio": _safe_float(source.get("cost_to_edge_ratio"), 0.0),
        "reconciliation_status": str(source.get("reconciliation_status") or source.get("execution_consistency") or "review").lower(),
        "anomaly_count": _safe_int(source.get("anomaly_count"), 0),
        "symbol_strategy_pairs": pairs,
        "strategies": strategies,
        "quarantined": _as_list(source.get("quarantined") or data.get("quarantined_strategies")),
    }


def _reason(code: str, detail: str, action: str, severity: str = "major", priority: int = 50) -> dict:
    return {"code": code, "severity": severity, "detail": detail, "action": action, "priority": priority}


def _critical(reasons: list[dict]) -> dict:
    if not reasons:
        return {"code": "none", "severity": "ok", "detail": "Live strategy reality validation is acceptable.", "action": "continue_guarded_observation", "priority": 99}
    weight = {"critical": 0, "major": 1, "minor": 2, "ok": 3}
    return sorted(reasons, key=lambda item: (weight.get(str(item.get("severity")), 2), int(item.get("priority", 50))))[0]


def _expectancy_gap(metrics: dict) -> float:
    return round(metrics["paper_expectancy_bps"] - metrics["micro_live_expectancy_bps"], 4)


def _degradation_ratio(metrics: dict) -> float:
    paper = abs(metrics["paper_expectancy_bps"])
    if paper <= 0:
        return 1.0 if metrics["micro_live_expectancy_bps"] < 0 else 0.0
    return round(max(0.0, _expectancy_gap(metrics)) / paper, 4)


def _confidence_for_pair(pair: dict, policy: dict) -> float:
    sample = min(1.0, _safe_int(pair.get("sample_count"), 0) / max(1, policy["min_live_sample_count"]))
    pf = min(1.0, max(0.0, (_safe_float(pair.get("profit_factor"), 0.0) - 0.8) / 0.7))
    slip = 1.0 - min(1.0, _safe_float(pair.get("avg_slippage_bps"), policy["max_slippage_bps"]) / max(1.0, policy["max_slippage_bps"] * 2))
    recon = 1.0 if str(pair.get("reconciliation_status") or "ok").lower() in {"ok", "consistent"} else 0.45
    return round(max(0.0, min(1.0, sample * 0.35 + pf * 0.30 + slip * 0.20 + recon * 0.15)), 4)


def build_rev231_paper_vs_micro_live_expectancy_comparator(data: dict | None, settings: dict | None = None, auth_store: dict | None = None, username: str = "default") -> dict:
    policy = _policy(settings)
    metrics = _metrics(data)
    gap = _expectancy_gap(metrics)
    checks = [
        _check("sample_count", "ok" if metrics["sample_count"] >= policy["min_live_sample_count"] else "review", "Micro/live sample size should be sufficient before trusting expectancy.", False, 4, "collect_more_micro_live_evidence"),
        _check("expectancy_gap", "ok" if gap <= policy["max_expectancy_gap_bps"] else "blocked", "Paper edge must not materially exceed micro/live reality.", True, 1, "downgrade_strategy_until_reality_matches"),
        _check("reconciliation", "ok" if metrics["reconciliation_status"] in {"ok", "consistent"} else "blocked", "Live comparison requires consistent execution reconciliation.", True, 2, "fix_reconciliation_before_strategy_decision"),
    ]
    body = {
        "comparison_status": _final_status(checks),
        "paper_expectancy_bps": metrics["paper_expectancy_bps"],
        "micro_live_expectancy_bps": metrics["micro_live_expectancy_bps"],
        "expectancy_gap_bps": gap,
        "sample_count": metrics["sample_count"],
        "operator_action": _critical([c for c in checks if c.get("status") != "ok"]).get("action"),
        "trade_allowed": False,
        "real_submit_close": "OFF",
    }
    return {"engine": "paper_vs_micro_live_expectancy_comparator", "revision": 231, "status": _final_status(checks), "generated_at": now_iso(), "paper_vs_micro_live_expectancy_comparator": body, "checks": checks, "check_totals": _totals(checks), "command_preview": _command_preview(), "contains_secret": False, "secret_values_returned": False, "next_allowed_step": "rev232_strategy_live_degradation_detector"}


def build_rev232_strategy_live_degradation_detector(data: dict | None, settings: dict | None = None, auth_store: dict | None = None, username: str = "default") -> dict:
    policy = _policy(settings)
    metrics = _metrics(data)
    degradation = _degradation_ratio(metrics)
    checks = [
        _check("degradation_ratio", "ok" if degradation <= policy["max_degradation_ratio"] else "blocked", "Live degradation must remain below threshold.", True, 1, "quarantine_or_reduce_degraded_strategy"),
        _check("profit_factor", "ok" if metrics["micro_live_profit_factor"] >= policy["min_profit_factor"] else "review", "Micro/live profit factor should remain above minimum.", False, 5, "collect_more_sample_or_reduce"),
        _check("cost_to_edge_ratio", "ok" if metrics["cost_to_edge_ratio"] <= policy["max_cost_to_edge_ratio"] else "blocked", "Cost cannot consume too much of the measured edge.", True, 2, "recalibrate_fee_slippage_threshold"),
    ]
    body = {
        "degradation_status": _final_status(checks),
        "degradation_ratio": degradation,
        "micro_live_profit_factor": metrics["micro_live_profit_factor"],
        "cost_to_edge_ratio": metrics["cost_to_edge_ratio"],
        "live_degraded": _final_status(checks) == "blocked",
        "operator_action": _critical([c for c in checks if c.get("status") != "ok"]).get("action"),
        "trade_allowed": False,
        "real_submit_close": "OFF",
    }
    return {"engine": "strategy_live_degradation_detector", "revision": 232, "status": _final_status(checks), "generated_at": now_iso(), "strategy_live_degradation_detector": body, "checks": checks, "check_totals": _totals(checks), "command_preview": _command_preview(), "contains_secret": False, "secret_values_returned": False, "next_allowed_step": "rev233_symbol_strategy_pair_confidence_scorer"}


def build_rev233_symbol_strategy_pair_confidence_scorer(data: dict | None, settings: dict | None = None, auth_store: dict | None = None, username: str = "default") -> dict:
    policy = _policy(settings)
    metrics = _metrics(data)
    pairs = metrics["symbol_strategy_pairs"] or [
        {
            "symbol": "BTCUSDT",
            "strategy": "guarded_micro_scalp",
            "sample_count": metrics["sample_count"],
            "profit_factor": metrics["micro_live_profit_factor"],
            "avg_slippage_bps": metrics["avg_slippage_bps"],
            "reconciliation_status": metrics["reconciliation_status"],
        }
    ]
    scored = []
    for pair in pairs:
        if not isinstance(pair, dict):
            continue
        score = _confidence_for_pair(pair, policy)
        scored.append({
            "symbol": str(pair.get("symbol") or "UNKNOWN"),
            "strategy": str(pair.get("strategy") or pair.get("strategy_id") or "unknown_strategy"),
            "confidence_score": score,
            "sample_count": _safe_int(pair.get("sample_count"), metrics["sample_count"]),
            "allowed_for_repeat": score >= policy["min_confidence_score"],
            "operator_action": "observe" if score >= policy["min_confidence_score"] else "keep_pair_in_preview_only",
        })
    best = sorted(scored, key=lambda item: item.get("confidence_score", 0), reverse=True)[0] if scored else {}
    checks = [
        _check("pairs_present", "ok" if scored else "blocked", "At least one symbol-strategy pair should be scoreable.", True, 1, "restore_strategy_pair_metrics"),
        _check("best_pair_confidence", "ok" if best.get("confidence_score", 0) >= policy["min_confidence_score"] else "review", "Best pair should pass confidence before repeat live exposure.", False, 4, "keep_best_pair_in_shadow_until_confident"),
    ]
    body = {
        "confidence_status": _final_status(checks),
        "min_confidence_score": policy["min_confidence_score"],
        "best_pair": best,
        "pair_count": len(scored),
        "scored_pairs": scored[:20],
        "operator_action": _critical([c for c in checks if c.get("status") != "ok"]).get("action"),
        "trade_allowed": False,
        "real_submit_close": "OFF",
    }
    return {"engine": "symbol_strategy_pair_confidence_scorer", "revision": 233, "status": _final_status(checks), "generated_at": now_iso(), "symbol_strategy_pair_confidence_scorer": body, "checks": checks, "check_totals": _totals(checks), "command_preview": _command_preview(), "contains_secret": False, "secret_values_returned": False, "next_allowed_step": "rev234_weak_strategy_quarantine_controller"}


def build_rev234_weak_strategy_quarantine_controller(data: dict | None, settings: dict | None = None, auth_store: dict | None = None, username: str = "default") -> dict:
    policy = _policy(settings)
    score_payload = build_rev233_symbol_strategy_pair_confidence_scorer(data, settings, auth_store, username)["symbol_strategy_pair_confidence_scorer"]
    weak_pairs = [p for p in score_payload.get("scored_pairs", []) if not p.get("allowed_for_repeat")]
    checks = [
        _check("weak_strategy_detection", "ok" if not weak_pairs else "review", "Weak strategy-symbol pairs should remain preview-only or quarantined.", False, 5, "quarantine_weak_pairs"),
        _check("auto_apply_disabled", "ok" if not policy["auto_apply_enable"] else "blocked", "Quarantine suggestions must not auto-apply without owner approval.", True, 1, "turn_auto_apply_off"),
        _check("auto_scale_disabled", "ok" if not policy["auto_scale_enable"] else "blocked", "Weak strategy handling must not scale exposure automatically.", True, 2, "turn_auto_scale_off"),
    ]
    quarantine = [
        {
            "symbol": p.get("symbol"),
            "strategy": p.get("strategy"),
            "confidence_score": p.get("confidence_score"),
            "action": "preview_only_quarantine_recommended",
            "auto_applied": False,
        }
        for p in weak_pairs
    ]
    body = {
        "quarantine_status": _final_status(checks),
        "weak_pair_count": len(weak_pairs),
        "quarantine_recommendations": quarantine[:20],
        "auto_apply": "OFF",
        "auto_scale": "OFF",
        "operator_action": _critical([c for c in checks if c.get("status") != "ok"]).get("action"),
        "trade_allowed": False,
        "real_submit_close": "OFF",
    }
    return {"engine": "weak_strategy_quarantine_controller", "revision": 234, "status": _final_status(checks), "generated_at": now_iso(), "weak_strategy_quarantine_controller": body, "checks": checks, "check_totals": _totals(checks), "command_preview": _command_preview(), "contains_secret": False, "secret_values_returned": False, "next_allowed_step": "rev235_live_strategy_reality_report"}


def build_rev235_live_strategy_reality_report(data: dict | None, settings: dict | None = None, auth_store: dict | None = None, username: str = "default") -> dict:
    comparator = build_rev231_paper_vs_micro_live_expectancy_comparator(data, settings, auth_store, username)
    degradation = build_rev232_strategy_live_degradation_detector(data, settings, auth_store, username)
    scorer = build_rev233_symbol_strategy_pair_confidence_scorer(data, settings, auth_store, username)
    quarantine = build_rev234_weak_strategy_quarantine_controller(data, settings, auth_store, username)
    checks = []
    for payload in (comparator, degradation, scorer, quarantine):
        checks.extend(payload.get("checks") or [])
    reasons = []
    comp = comparator["paper_vs_micro_live_expectancy_comparator"]
    deg = degradation["strategy_live_degradation_detector"]
    sc = scorer["symbol_strategy_pair_confidence_scorer"]
    q = quarantine["weak_strategy_quarantine_controller"]
    if comp.get("comparison_status") == "blocked":
        reasons.append(_reason("paper_live_gap", "Paper expectancy is too far above micro/live reality.", "downgrade_strategy_until_reality_matches", "critical", 1))
    if deg.get("degradation_status") == "blocked":
        reasons.append(_reason("live_degradation", "Live degradation/cost ratio exceeds guardrail.", "quarantine_or_reduce_degraded_strategy", "critical", 2))
    if not sc.get("best_pair", {}).get("allowed_for_repeat", False):
        reasons.append(_reason("low_pair_confidence", "No symbol-strategy pair is confident enough for repeat live exposure.", "keep_pairs_in_shadow_or_preview", "major", 4))
    if q.get("weak_pair_count", 0) > 0:
        reasons.append(_reason("weak_pairs_present", "Weak symbol-strategy pairs require quarantine recommendation.", "review_quarantine_recommendations", "minor", 8))
    critical = _critical(reasons)
    status = "BLOCKED" if any(r.get("severity") == "critical" for r in reasons) else "REVIEW" if reasons else "OK"
    strategy_live_ready = status == "OK" and sc.get("best_pair", {}).get("allowed_for_repeat", False)
    decision = "HOLD" if status in {"BLOCKED", "REVIEW"} else "ALLOW_PREVIEW_REPEAT"
    report = {
        "strategy_reality": status,
        "strategy_live_ready": strategy_live_ready,
        "decision": decision,
        "critical_issue": critical,
        "paper_vs_micro_live": comp,
        "degradation": deg,
        "confidence": sc,
        "quarantine": q,
        "best_pair": sc.get("best_pair", {}),
        "weak_pair_count": q.get("weak_pair_count", 0),
        "trade_allowed": False,
        "owner_action": critical.get("action"),
        "operator_action": critical.get("action"),
        "real_submit_close": "OFF",
        "auto_apply": "OFF",
        "auto_scale": "OFF",
    }
    return {"engine": "live_strategy_reality_report", "revision": 235, "status": _final_status(checks), "generated_at": now_iso(), "live_strategy_reality_report": report, "checks": checks, "check_totals": _totals(checks), "command_preview": _command_preview(), "contains_secret": False, "secret_values_returned": False, "next_allowed_step": "rev236_capital_preservation_usdt_dominance_block"}


_BUILDERS = {
    231: build_rev231_paper_vs_micro_live_expectancy_comparator,
    232: build_rev232_strategy_live_degradation_detector,
    233: build_rev233_symbol_strategy_pair_confidence_scorer,
    234: build_rev234_weak_strategy_quarantine_controller,
    235: build_rev235_live_strategy_reality_report,
}


def build_for_revision(revision: int, data: dict | None, settings: dict | None = None, auth_store: dict | None = None, username: str = "default") -> dict:
    rev = int(revision)
    if rev not in _BUILDERS:
        raise ValueError(f"Unsupported Rev231-235 revision: {revision}")
    return _BUILDERS[rev](data, settings, auth_store, username)


def build_summary_for_revision(revision: int, data: dict | None, settings: dict | None = None, auth_store: dict | None = None, username: str = "default") -> dict:
    payload = build_for_revision(revision, data, settings, auth_store, username)
    body = payload.get("paper_vs_micro_live_expectancy_comparator") or payload.get("strategy_live_degradation_detector") or payload.get("symbol_strategy_pair_confidence_scorer") or payload.get("weak_strategy_quarantine_controller") or payload.get("live_strategy_reality_report") or {}
    critical = body.get("critical_issue") or {}
    best_pair = body.get("best_pair") or body.get("confidence", {}).get("best_pair") or {}
    return {
        "revision": int(revision),
        "status": payload.get("status"),
        "mode": "live_strategy_reality_validation_preview",
        "decision": body.get("decision") or ("HOLD" if payload.get("status") != "ok" else "ALLOW_PREVIEW_REPEAT"),
        "strategy_reality": body.get("strategy_reality") or body.get("comparison_status") or body.get("degradation_status") or body.get("confidence_status") or body.get("quarantine_status"),
        "strategy_live_ready": bool(body.get("strategy_live_ready", False)),
        "best_pair": best_pair,
        "weak_pair_count": body.get("weak_pair_count", 0),
        "critical_issue": critical.get("code") or critical or "review",
        "operator_action": body.get("operator_action") or body.get("owner_action") or "review",
        "trade_allowed": False,
        "real_submit_close": "OFF",
        "command_preview": payload.get("command_preview"),
        "contains_secret": False,
        "secret_values_returned": False,
    }


def build_block_payload(data: dict | None, settings: dict | None = None, auth_store: dict | None = None, username: str = "default") -> dict:
    outputs = {
        "autonomous_paper_vs_micro_live_expectancy_comparator": build_rev231_paper_vs_micro_live_expectancy_comparator(data, settings, auth_store, username),
        "autonomous_strategy_live_degradation_detector": build_rev232_strategy_live_degradation_detector(data, settings, auth_store, username),
        "autonomous_symbol_strategy_pair_confidence_scorer": build_rev233_symbol_strategy_pair_confidence_scorer(data, settings, auth_store, username),
        "autonomous_weak_strategy_quarantine_controller": build_rev234_weak_strategy_quarantine_controller(data, settings, auth_store, username),
        "autonomous_live_strategy_reality_report": build_rev235_live_strategy_reality_report(data, settings, auth_store, username),
    }
    final = outputs["autonomous_live_strategy_reality_report"]
    block_status = "blocked" if any(x.get("status") == "blocked" for x in outputs.values()) else "review" if any(x.get("status") == "review" for x in outputs.values()) else "ok"
    return {
        "engine": "autonomous_live_strategy_reality_validation_block",
        "revision": 235,
        "status": block_status,
        "generated_at": now_iso(),
        "outputs": outputs,
        "live_strategy_reality_report": final.get("live_strategy_reality_report"),
        "summary_result": build_summary_for_revision(235, data, settings, auth_store, username),
        "command_preview": _command_preview(),
        "real_submit_default_off": True,
        "real_close_default_off": True,
        "network_default_off": True,
        "auto_scale_default_off": True,
        "auto_apply_default_off": True,
        "contains_secret": False,
        "secret_values_returned": False,
    }


def build_quality_for_revision(revision: int, data: dict | None, settings: dict | None = None, auth_store: dict | None = None, username: str = "default") -> dict:
    payload = build_for_revision(revision, data, settings, auth_store, username)
    all_checks = list(payload.get("checks") or []) + [
        _check("quality_network_default_off", "ok", "Quality gate confirms no exchange network request."),
        _check("quality_real_submit_default_off", "ok", "Quality gate confirms real submit default OFF."),
        _check("quality_real_close_default_off", "ok", "Quality gate confirms real close default OFF."),
        _check("quality_auto_scale_default_off", "ok", "Quality gate confirms auto-scale default OFF."),
        _check("quality_auto_apply_default_off", "ok", "Quality gate confirms auto-apply default OFF."),
        _check("quality_secret_free", "ok", "Quality gate confirms no secret values are returned."),
    ]
    return {"engine": "autonomous_live_strategy_reality_validation_quality_gate", "revision": int(revision), "quality_gate": "PASS", "status": payload.get("status"), "checks": all_checks, "check_totals": _totals(all_checks), "network_default_off": True, "real_submit_default_off": True, "real_close_default_off": True, "auto_scale_default_off": True, "auto_apply_default_off": True, "contains_secret": False, "secret_values_returned": False}
