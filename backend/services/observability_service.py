from __future__ import annotations

import os
import time
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from services.real_trade_safety_service import build_runtime_health

STARTED_AT = time.time()
REVISION = "29"


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def safe_float(value: Any, default: float = 0.0) -> float:
    try:
        number = float(value)
        if number != number:
            return default
        return number
    except Exception:
        return default


def safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(float(value))
    except Exception:
        return default


def parse_time(value: Any):
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except Exception:
        return None


def age_seconds(value: Any) -> int | None:
    stamp = parse_time(value)
    if not stamp:
        return None
    try:
        if stamp.tzinfo is None:
            stamp = stamp.replace(tzinfo=timezone.utc)
        return max(int((datetime.now(timezone.utc) - stamp).total_seconds()), 0)
    except Exception:
        return None


def status_from_score(score: float) -> str:
    if score >= 85:
        return "ok"
    if score >= 65:
        return "review"
    return "blocked"


def get_logs(data: dict) -> list[dict]:
    logs = data.get("logs") or []
    return logs if isinstance(logs, list) else []


def get_audit(data: dict) -> list[dict]:
    audit = data.get("audit") or []
    return audit if isinstance(audit, list) else []


def get_health_history(data: dict) -> list[dict]:
    history = data.get("health_history") or []
    return history if isinstance(history, list) else []


def build_endpoint_error_report(data: dict) -> dict:
    logs = get_logs(data)
    audit = get_audit(data)
    endpoint_counter = Counter()
    error_counter = Counter()
    recent = []

    for item in audit:
        endpoint = str(item.get("endpoint") or item.get("path") or "-")
        result = str(item.get("result") or item.get("status") or "").lower()
        severity = str(item.get("severity") or "").lower()
        if endpoint != "-":
            endpoint_counter[endpoint] += 1
        if result in {"error", "failed", "blocked"} or severity in {"critical", "blocked"}:
            error_counter[endpoint] += 1
            recent.append({
                "time": item.get("timestamp") or item.get("time") or "-",
                "endpoint": endpoint,
                "action": item.get("action") or "-",
                "severity": severity or "-",
                "result": result or "-",
                "message": item.get("message") or "-",
            })

    for item in logs:
        level = str(item.get("level") or item.get("type") or "").lower()
        if level in {"error", "warn", "warning"}:
            key = str(item.get("event") or item.get("source") or "log")
            error_counter[key] += 1
            recent.append({
                "time": item.get("timestamp") or item.get("time") or "-",
                "endpoint": key,
                "action": item.get("event") or "runtime_log",
                "severity": "warning" if level.startswith("warn") else "critical",
                "result": level,
                "message": item.get("message") or "-",
            })

    total_calls = sum(endpoint_counter.values())
    total_errors = sum(error_counter.values())
    error_rate = (total_errors / total_calls * 100) if total_calls else 0.0
    return {
        "status": "ok" if error_rate < 5 else ("review" if error_rate < 20 else "blocked"),
        "total_observed_calls": total_calls,
        "total_errors": total_errors,
        "error_rate_pct": round(error_rate, 2),
        "top_endpoints": endpoint_counter.most_common(10),
        "top_errors": error_counter.most_common(10),
        "recent_errors": list(reversed(recent[-20:])),
    }


def build_latency_report(data: dict) -> dict:
    last_scan = data.get("last_scan") or {}
    bot_traces = data.get("bot_loop_traces") or []
    health_history = get_health_history(data)
    binance_latency = safe_float(last_scan.get("latency_ms") or last_scan.get("binance_latency_ms"))
    backend_latency = safe_float(data.get("backend_latency_ms"))
    durations = [safe_float(item.get("duration_ms") or item.get("duration_seconds", 0) * 1000) for item in bot_traces[-50:] if isinstance(item, dict)]
    health_durations = [safe_float(item.get("duration_ms")) for item in health_history[-50:] if isinstance(item, dict) and item.get("duration_ms")]
    all_durations = [x for x in (durations + health_durations) if x > 0]
    avg_loop = round(sum(all_durations) / len(all_durations), 2) if all_durations else 0.0
    max_loop = round(max(all_durations), 2) if all_durations else 0.0
    warnings = []
    if binance_latency > 1500:
        warnings.append("binance_latency_high")
    if avg_loop > 5000:
        warnings.append("bot_loop_slow")
    if max_loop > 15000:
        warnings.append("bot_loop_spike")
    return {
        "status": "ok" if not warnings else "review",
        "backend_latency_ms": round(backend_latency, 2),
        "binance_latency_ms": round(binance_latency, 2),
        "bot_loop_avg_ms": avg_loop,
        "bot_loop_max_ms": max_loop,
        "samples": len(all_durations),
        "warnings": warnings,
    }


def build_stale_report(data: dict, settings: dict) -> dict:
    last_scan = data.get("last_scan") or {}
    runtime = build_runtime_health(data, settings)
    scan_age = age_seconds(last_scan.get("time") or last_scan.get("generated_at") or last_scan.get("created_at"))
    tick_age = age_seconds(data.get("last_tick") or data.get("last_updated_at"))
    paper_age = age_seconds(data.get("last_paper_lab_tick") or data.get("last_model_evaluation_at"))
    blockers = []
    if scan_age is None:
        blockers.append("scan_timestamp_missing")
    elif scan_age > 900:
        blockers.append("scan_stale")
    if data.get("bot_running") and tick_age is not None and tick_age > 180:
        blockers.append("bot_tick_stale")
    if runtime.get("status") not in {"ok", "healthy"}:
        blockers.extend(runtime.get("problems") or [])
    return {
        "status": "ok" if not blockers else ("review" if len(blockers) <= 2 else "blocked"),
        "scan_age_seconds": scan_age,
        "bot_tick_age_seconds": tick_age,
        "paper_lab_age_seconds": paper_age,
        "runtime_status": runtime.get("status"),
        "blockers": list(dict.fromkeys(blockers)),
        "runtime_health": runtime,
    }


def build_deploy_report(data: dict) -> dict:
    repo_root = Path(__file__).resolve().parents[2]
    deploy_markers = {
        "deploy_script": (repo_root / "deploy" / "deploy.sh").exists(),
        "backend_service": (repo_root / "deploy" / "hmtstc-backend.service").exists(),
        "nginx_conf": (repo_root / "deploy" / "nginx.conf").exists(),
        "webhook_server": (repo_root / "webhook_server.py").exists(),
    }
    revision_meta = data.get("revision") or data.get("deploy") or {}
    return {
        "status": "ok" if all(deploy_markers.values()) else "review",
        "current_revision": REVISION,
        "app_uptime_seconds": int(time.time() - STARTED_AT),
        "deploy_markers": deploy_markers,
        "revision_meta": revision_meta,
        "locked_after_deploy_policy": True,
        "shadow_first_policy": True,
    }


def build_observability_summary(data: dict, settings: dict) -> dict:
    latency = build_latency_report(data)
    errors = build_endpoint_error_report(data)
    stale = build_stale_report(data, settings)
    deploy = build_deploy_report(data)
    score = 100
    for report in (latency, errors, stale, deploy):
        if report.get("status") == "review":
            score -= 12
        elif report.get("status") == "blocked":
            score -= 28
    score = max(score, 0)
    warnings = []
    warnings.extend(latency.get("warnings") or [])
    warnings.extend(stale.get("blockers") or [])
    if errors.get("total_errors"):
        warnings.append("endpoint_errors_observed")
    status = status_from_score(score)
    return {
        "status": status,
        "score": score,
        "generated_at": now_iso(),
        "revision": REVISION,
        "latency": latency,
        "endpoint_errors": errors,
        "stale_data": stale,
        "deploy": deploy,
        "warnings": list(dict.fromkeys(warnings)),
        "policy": {
            "real_trading_locked_by_default": True,
            "observability_does_not_unlock_real_trade": True,
            "degraded_health_blocks_real_order": True,
        },
    }


def build_observability_ui_contract() -> dict:
    return {
        "status": "ok",
        "required_panels": [
            "dashboard_compact_health",
            "intelligence_detailed_health",
            "endpoint_error_rate",
            "binance_latency",
            "deploy_revision_health",
            "critical_warnings",
        ],
        "dashboard_fields": ["score", "status", "binance_latency_ms", "endpoint_error_rate_pct", "stale_status"],
        "intelligence_fields": ["latency", "endpoint_errors", "stale_data", "deploy", "warnings"],
    }
