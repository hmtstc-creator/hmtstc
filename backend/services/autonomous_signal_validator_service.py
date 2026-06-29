from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
from typing import Any



def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


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
        return value.strip().lower() in {"1", "true", "yes", "on", "enabled"}
    if value is None:
        return fallback
    return bool(value)


def _clamp(value: float, low: float = 0.0, high: float = 100.0) -> float:
    return max(low, min(high, value))


def _policy(settings: dict | None) -> dict:
    settings = settings if isinstance(settings, dict) else {}
    raw = settings.get("autonomous_signal_validator") if isinstance(settings.get("autonomous_signal_validator"), dict) else {}
    return {
        "enabled": _safe_bool(raw.get("enabled"), True),
        "min_validation_score": _clamp(_safe_float(raw.get("min_validation_score"), 68.0), 1.0, 100.0),
        "min_learning_score": _clamp(_safe_float(raw.get("min_learning_score"), 45.0), 1.0, 100.0),
        "min_route_score": _clamp(_safe_float(raw.get("min_route_score"), 62.0), 1.0, 100.0),
        "max_blockers": max(0, min(10, _safe_int(raw.get("max_blockers"), 0))),
        "allow_paper_when_review": _safe_bool(raw.get("allow_paper_when_review"), True),
        "read_only": True,
        "auto_apply": False,
    }


def _scan_candidates(data: dict) -> list[dict]:
    scan = data.get("last_scan") if isinstance(data.get("last_scan"), dict) else {}
    rows = scan.get("scan_rows") if isinstance(scan.get("scan_rows"), list) else data.get("scan_rows")
    rows = rows if isinstance(rows, list) else []
    candidates: list[dict] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        symbol = str(row.get("symbol") or row.get("pair") or "").upper().strip()
        if not symbol:
            continue
        score = _clamp(_safe_float(row.get("route_score") or row.get("score") or row.get("source_score"), 0.0))
        status = str(row.get("status") or "WATCH").upper()
        if status in {"REJECT", "BLOCKED"}:
            continue
        candidates.append({
            "symbol": symbol,
            "strategy": str(row.get("strategy") or row.get("strategy_hint") or "micro_scalp_watch"),
            "route_score": score,
            "route_action": "PAPER_ROUTE" if score >= 55 else "WATCH_ROUTE",
            "spread_pct": row.get("spread_pct"),
            "volatility": row.get("volatility"),
        })
    return sorted(candidates, key=lambda item: item["route_score"], reverse=True)



def _performance_state_from_data(data: dict) -> str:
    trades = data.get("closed_trades") if isinstance(data.get("closed_trades"), list) else []
    recent = [item for item in trades[-5:] if isinstance(item, dict)]
    if len(recent) >= 3:
        losses = 0
        for trade in reversed(recent):
            if _safe_float(trade.get("pnl_usdt", trade.get("pnl", 0.0))) < 0:
                losses += 1
            else:
                break
        if losses >= 3:
            return "COOLDOWN"
    return str(data.get("performance_state") or "WATCH")

def _router_view(data: dict) -> dict:
    existing = data.get("autonomous_opportunity_router") if isinstance(data.get("autonomous_opportunity_router"), dict) else {}
    if existing:
        return existing
    routes = _scan_candidates(data)
    primary = routes[0] if routes else {}
    state = "ROUTE_READY" if primary and primary.get("route_score", 0) >= 62 else ("WATCH" if primary else "WAIT")
    return {
        "revision": 76,
        "route_state": state,
        "primary_action": primary.get("route_action", "WAIT"),
        "primary_symbol": primary.get("symbol"),
        "primary_strategy": primary.get("strategy"),
        "routes": routes[:5],
        "blockers": [],
        "warnings": [],
        "inputs": {
            "performance_revision": 75,
            "performance_state": _performance_state_from_data(data),
        },
    }


def _top_route(router: dict) -> dict:
    routes = router.get("routes") if isinstance(router.get("routes"), list) else []
    for route in routes:
        if isinstance(route, dict):
            return route
    return {}


def _learning_score(memory: dict) -> float:
    candidates = [
        memory.get("learning_score"),
        memory.get("score"),
        memory.get("memory_score"),
    ]
    for value in candidates:
        score = _safe_float(value, -1.0)
        if score >= 0:
            return _clamp(score)
    return 55.0


def _evidence_items(data: dict, router: dict) -> list[str]:
    items: list[str] = []
    route_state = router.get("route_state")
    primary_action = router.get("primary_action")
    if route_state:
        items.append(f"router_state:{route_state}")
    if primary_action:
        items.append(f"primary_action:{primary_action}")
    for key in ("learning_gaps", "recommendations", "evidence", "evidence_items"):
        values = data.get(key)
        if isinstance(values, list):
            items.extend(str(v) for v in values[:5] if v)
    return sorted(set(items))[:12]


def _validation_score(route: dict, router: dict, data: dict, policy: dict) -> tuple[float, list[str], list[str]]:
    blockers: set[str] = set()
    warnings: set[str] = set()
    route_score = _safe_float(route.get("route_score"), 0.0)
    learning_score = _clamp(_safe_float(data.get("learning_score") or data.get("memory_score"), 55.0))
    route_state = str(router.get("route_state") or "WAIT").upper()
    inputs = router.get("inputs") if isinstance(router.get("inputs"), dict) else {}
    performance_state = str(inputs.get("performance_state") or "UNKNOWN").upper()
    route_action = str(route.get("route_action") or router.get("primary_action") or "WAIT").upper()

    if not policy["enabled"]:
        blockers.add("signal_validator_disabled")
    if route_state in {"BLOCKED", "DISABLED"}:
        blockers.add("router_not_tradeable")
    if "safety" in " ".join(router.get("blockers") or []).lower():
        blockers.add("safety_supervisor_blocks_signal")
    if performance_state in {"STOP_AND_PROTECT", "COOLDOWN"}:
        blockers.add("performance_sentinel_blocks_signal")
    if not route:
        blockers.add("no_primary_route")
    if route_score < policy["min_route_score"]:
        warnings.add("route_score_below_validation_policy")
    if learning_score < policy["min_learning_score"]:
        warnings.add("learning_score_below_policy")
    if route_action in {"SKIP_ROUTE", "WAIT", "WATCH_ROUTE"}:
        warnings.add("route_action_not_directly_executable")

    score = route_score * 0.56 + learning_score * 0.22
    score += 12.0 if route_state == "ROUTE_READY" else 0.0
    score += 8.0 if route_action in {"PAPER_ROUTE", "MICRO_REAL_ROUTE", "REAL_ROUTE"} else -4.0
    score += 6.0 if performance_state in {"CONTINUE", "LOCK_PROFIT", "WATCH", "UNKNOWN"} else -10.0
    score -= len(blockers) * 24.0
    score -= len(warnings) * 5.0
    return round(_clamp(score), 2), sorted(blockers), sorted(warnings)


def _decision(score: float, blockers: list[str], warnings: list[str], route: dict, policy: dict) -> str:
    action = str(route.get("route_action") or "WAIT").upper()
    if blockers:
        return "REJECT_SIGNAL"
    if score >= policy["min_validation_score"] and action in {"MICRO_REAL_ROUTE", "REAL_ROUTE"}:
        return "APPROVE_EXECUTION_PREVIEW"
    if score >= policy["min_validation_score"] and action == "PAPER_ROUTE":
        return "APPROVE_PAPER_PREVIEW"
    if policy["allow_paper_when_review"] and action in {"WATCH_ROUTE", "PAPER_ROUTE"} and score >= max(45.0, policy["min_validation_score"] - 18.0):
        return "PAPER_ONLY_REVIEW"
    if warnings:
        return "REVIEW_SIGNAL"
    return "WAIT"


def build_autonomous_signal_validator(
    data: dict | None,
    settings: dict | None = None,
    auth_store: dict | None = None,
    username: str = "default",
) -> dict:
    """Rev77 read-only signal validator.

    Validates the best opportunity route before any future execution path by
    combining router output, safety state, learning evidence and performance
    context. It never places orders and never writes runtime state.
    """
    data = deepcopy(data or {})
    settings = deepcopy(settings or {})
    auth_store = deepcopy(auth_store or {})
    policy = _policy(settings)
    router = _router_view(data)
    route = _top_route(router)
    score, blockers, warnings = _validation_score(route, router, data, policy)
    decision = _decision(score, blockers, warnings, route, policy)
    evidence = _evidence_items(data, router)
    status = "ok" if decision in {"APPROVE_EXECUTION_PREVIEW", "APPROVE_PAPER_PREVIEW"} else ("blocked" if blockers else "review")
    return {
        "status": status,
        "revision": 77,
        "engine": "autonomous_signal_validator",
        "generated_at": now_iso(),
        "read_only": True,
        "auto_apply": False,
        "validation_state": "VALIDATED" if status == "ok" else ("BLOCKED" if blockers else "REVIEW"),
        "validation_decision": decision,
        "validation_score": score,
        "symbol": route.get("symbol") or router.get("primary_symbol"),
        "strategy": route.get("strategy") or router.get("primary_strategy"),
        "route_action": route.get("route_action") or router.get("primary_action"),
        "blockers": blockers,
        "warnings": warnings,
        "evidence": evidence,
        "inputs": {
            "router_revision": router.get("revision"),
            "safety_revision": 71,
            "memory_revision": 72,
            "performance_revision": router.get("inputs", {}).get("performance_revision"),
            "route_state": router.get("route_state"),
            "route_score": route.get("route_score"),
            "learning_score": _clamp(_safe_float(data.get("learning_score") or data.get("memory_score"), 55.0)),
            "performance_state": router.get("inputs", {}).get("performance_state"),
        },
        "policy": policy,
        "command_preview": {
            "type": "signal_validation_preview",
            "read_only": True,
            "auto_apply": False,
            "places_order": False,
            "writes_runtime_state": False,
            "requires_opportunity_router": True,
            "requires_safety_supervisor": True,
            "source_revision": 77,
            "decision": decision,
            "symbol": route.get("symbol") or router.get("primary_symbol"),
            "strategy": route.get("strategy") or router.get("primary_strategy"),
        },
    }


def _summary_from_payload(payload: dict) -> dict:
    return {
        "status": payload.get("status"),
        "revision": 77,
        "engine": "autonomous_signal_validator_summary",
        "generated_at": payload.get("generated_at"),
        "read_only": True,
        "validation_state": payload.get("validation_state"),
        "validation_decision": payload.get("validation_decision"),
        "validation_score": payload.get("validation_score"),
        "symbol": payload.get("symbol"),
        "strategy": payload.get("strategy"),
        "attention_required": payload.get("status") in {"review", "blocked"},
        "blocker_count": len(payload.get("blockers") or []),
        "warning_count": len(payload.get("warnings") or []),
    }


def build_summary_autonomous_signal_validator(data: dict | None, settings: dict | None = None, auth_store: dict | None = None, username: str = "default") -> dict:
    return _summary_from_payload(build_autonomous_signal_validator(data, settings, auth_store, username))


def build_autonomous_signal_validator_quality(data: dict | None = None, settings: dict | None = None, auth_store: dict | None = None, username: str = "default") -> dict:
    payload = build_autonomous_signal_validator(data, settings, auth_store, username)
    summary = _summary_from_payload(payload)
    command = payload.get("command_preview") if isinstance(payload.get("command_preview"), dict) else {}
    inputs = payload.get("inputs") if isinstance(payload.get("inputs"), dict) else {}
    checks = {
        "revision_77": payload.get("revision") == 77 and summary.get("revision") == 77,
        "read_only": payload.get("read_only") is True and command.get("read_only") is True,
        "auto_apply_disabled": payload.get("auto_apply") is False and command.get("auto_apply") is False,
        "no_direct_order": command.get("places_order") is False,
        "no_runtime_persistence": command.get("writes_runtime_state") is False,
        "source_chain_visible": {"router_revision", "safety_revision", "memory_revision", "performance_revision"}.issubset(inputs.keys()),
        "validation_contract": {"validation_state", "validation_decision", "validation_score", "evidence"}.issubset(payload.keys()),
        "summary_minimal": {"validation_state", "validation_decision", "attention_required"}.issubset(summary.keys()),
        "no_secret_leak": "api_secret" not in str(payload).lower() and "secret_key" not in str(payload).lower(),
    }
    return {
        "status": "ok" if all(checks.values()) else "review",
        "revision": 77,
        "engine": "autonomous_signal_validator_quality",
        "generated_at": now_iso(),
        "checks": checks,
        "validation_state": payload.get("validation_state"),
        "validation_decision": payload.get("validation_decision"),
        "validation_score": payload.get("validation_score"),
    }
