from __future__ import annotations

import json
import os
import threading
from copy import deepcopy
from datetime import datetime, time, timedelta, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4
from zoneinfo import ZoneInfo

from core.config import BASE_DIR
from services.paper_lab_store import get_latest_paper_lab_run_any_user, list_paper_lab_runs
from services.real_trade_safety_service import build_runtime_health
from services.bot_runtime_truth_service import build_bot_runtime_truth


EIGHT_HOUR_REPORT_STORE_FILE = BASE_DIR / "eight_hour_report_store.json"
EIGHT_HOUR_REPORT_STORE_VERSION = 1
EIGHT_HOUR_REPORT_TIMEZONE = "Europe/Bucharest"
EIGHT_HOUR_REPORT_PERIODS = ("00:00-08:00", "08:00-16:00", "16:00-00:00")
_STORE_LOCK = threading.RLock()


def _now_local() -> datetime:
    return datetime.now(ZoneInfo(EIGHT_HOUR_REPORT_TIMEZONE))


def _empty_store() -> dict[str, Any]:
    return {
        "version": EIGHT_HOUR_REPORT_STORE_VERSION,
        "timezone": EIGHT_HOUR_REPORT_TIMEZONE,
        "periods": list(EIGHT_HOUR_REPORT_PERIODS),
        "updated_at": None,
        "reports": {},
    }


def _read_store() -> dict[str, Any]:
    with _STORE_LOCK:
        if not EIGHT_HOUR_REPORT_STORE_FILE.exists():
            return _empty_store()
        try:
            data = json.loads(EIGHT_HOUR_REPORT_STORE_FILE.read_text(encoding="utf-8"))
        except Exception:
            return _empty_store()
        if not isinstance(data, dict):
            return _empty_store()
        data.setdefault("version", EIGHT_HOUR_REPORT_STORE_VERSION)
        data.setdefault("timezone", EIGHT_HOUR_REPORT_TIMEZONE)
        data.setdefault("periods", list(EIGHT_HOUR_REPORT_PERIODS))
        data.setdefault("reports", {})
        if not isinstance(data["reports"], dict):
            data["reports"] = {}
        return data


def _write_store(data: dict[str, Any]) -> dict[str, Any]:
    with _STORE_LOCK:
        store = deepcopy(data)
        store["version"] = EIGHT_HOUR_REPORT_STORE_VERSION
        store["timezone"] = EIGHT_HOUR_REPORT_TIMEZONE
        store["periods"] = list(EIGHT_HOUR_REPORT_PERIODS)
        store["updated_at"] = datetime.now(timezone.utc).isoformat()
        EIGHT_HOUR_REPORT_STORE_FILE.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = EIGHT_HOUR_REPORT_STORE_FILE.with_name(f"{EIGHT_HOUR_REPORT_STORE_FILE.name}.{uuid4().hex}.tmp")
        try:
            tmp_path.write_text(json.dumps(store, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            os.replace(tmp_path, EIGHT_HOUR_REPORT_STORE_FILE)
        finally:
            if tmp_path.exists():
                try:
                    tmp_path.unlink()
                except Exception:
                    pass
        return store


def _last_completed_period(now: datetime | None = None) -> dict[str, Any]:
    local_now = now or _now_local()
    day = local_now.date()
    boundaries = [
        (time(0, 0), time(8, 0), "00:00-08:00"),
        (time(8, 0), time(16, 0), "08:00-16:00"),
        (time(16, 0), time(0, 0), "16:00-00:00"),
    ]

    if local_now.time() < time(8, 0):
        period_day = day - timedelta(days=1)
        start_t, end_t, label = boundaries[2]
    elif local_now.time() < time(16, 0):
        period_day = day
        start_t, end_t, label = boundaries[0]
    else:
        period_day = day
        start_t, end_t, label = boundaries[1]

    start_at = datetime.combine(period_day, start_t, tzinfo=ZoneInfo(EIGHT_HOUR_REPORT_TIMEZONE))
    if label == "16:00-00:00":
        end_at = datetime.combine(period_day + timedelta(days=1), time(0, 0), tzinfo=ZoneInfo(EIGHT_HOUR_REPORT_TIMEZONE))
    else:
        end_at = datetime.combine(period_day, end_t, tzinfo=ZoneInfo(EIGHT_HOUR_REPORT_TIMEZONE))

    return {
        "period": label,
        "period_key": f"{period_day.isoformat()}_{label}",
        "period_date": period_day.isoformat(),
        "started_at": start_at.isoformat(),
        "ended_at": end_at.isoformat(),
        "timezone": EIGHT_HOUR_REPORT_TIMEZONE,
    }


def _to_int(value: Any, fallback: int = 0) -> int:
    try:
        return int(float(value))
    except Exception:
        return fallback


def _sort_breakdown(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, dict):
        return []
    rows = [{"reason": str(key), "count": _to_int(count)} for key, count in value.items()]
    rows.sort(key=lambda item: item["count"], reverse=True)
    return rows


def build_bot_no_trade_reason_funnel(data: dict[str, Any], settings: dict[str, Any]) -> dict[str, Any]:
    username = str(settings.get("username") or settings.get("user") or data.get("username") or data.get("user") or "admin")
    runtime_truth = build_bot_runtime_truth(data, settings, username=username)
    scan = data.get("last_scan") if isinstance(data.get("last_scan"), dict) else {}
    rows = scan.get("scan_rows") if isinstance(scan.get("scan_rows"), list) else []
    candidates = scan.get("candidates") if isinstance(scan.get("candidates"), list) else []
    total = _to_int(scan.get("universe_total_seen"), _to_int(scan.get("scanned"), len(rows)))
    eligible = _to_int(scan.get("eligible_universe_count"), _to_int(scan.get("scanned"), len(rows)))
    universe_rejected = _to_int(scan.get("universe_rejected_count"), 0)
    coinfilter_passed = _to_int(scan.get("candidates_count"), len(candidates))
    coinfilter_rejected = _to_int(scan.get("rejected_count"), max(eligible - coinfilter_passed, 0)) + universe_rejected
    traces = data.get("bot_loop_traces") if isinstance(data.get("bot_loop_traces"), list) else []
    latest_tick = traces[-1] if traces and isinstance(traces[-1], dict) else {}
    opened_symbol = latest_tick.get("opened_symbol")
    paper_lab = data.get("paper_lab") if isinstance(data.get("paper_lab"), dict) else {}
    models = paper_lab.get("models") if isinstance(paper_lab.get("models"), dict) else {}
    active_models = [item for item in models.values() if isinstance(item, dict) and item.get("status", "active") == "active"]
    karabasan = data.get("karabasan") if isinstance(data.get("karabasan"), dict) else {}
    risk_state = data.get("risk_state") if isinstance(data.get("risk_state"), dict) else {}

    if runtime_truth.get("primary_runtime_problem") == "restore_no_first_tick":
        primary_reason = "bot_restore_failed"
    elif runtime_truth.get("requested_running") and not runtime_truth.get("loop_alive"):
        primary_reason = "bot_loop_stale"
    elif not scan:
        primary_reason = "scan_yok"
    elif scan.get("status") != "ok":
        primary_reason = scan.get("error") or scan.get("status") or "scan_not_ok"
    elif coinfilter_passed < 1:
        primary_reason = scan.get("top_rejection_reason") or "no_candidate"
    elif not active_models:
        primary_reason = "paper_lab_model_yok"
    elif not opened_symbol:
        primary_reason = "strategy_or_risk_no_trade"
    else:
        primary_reason = None

    return {
        "status": "ok",
        "engine_status": runtime_truth.get("engine_status"),
        "loop_alive": runtime_truth.get("loop_alive"),
        "requested_running": runtime_truth.get("requested_running"),
        "last_tick_age_seconds": runtime_truth.get("last_tick_age_seconds"),
        "last_scan_age_seconds": runtime_truth.get("last_scan_age_seconds"),
        "primary_runtime_problem": runtime_truth.get("primary_runtime_problem"),
        "scan_total": total,
        "coinfilter_passed": coinfilter_passed,
        "coinfilter_rejected": coinfilter_rejected,
        "strategy_signal_count": _to_int(latest_tick.get("strategy_signal_count") or scan.get("strategy_signal_count"), 0),
        "karabasan_passed": bool(karabasan.get("allow_trading", karabasan.get("passed", data.get("karabasan_passed", True)))),
        "risk_passed": bool(risk_state.get("passed", data.get("risk_passed", data.get("risk_gate_open", True)))),
        "final_trade_candidate_count": coinfilter_passed,
        "trade_opened": bool(opened_symbol),
        "opened_symbol": opened_symbol,
        "primary_no_trade_reason": primary_reason,
        "top_blockers": (_sort_breakdown(scan.get("universe_rejection_breakdown")) + _sort_breakdown(scan.get("rejection_breakdown")))[:10],
        "settings_snapshot": {
            "scan_limit": ((settings.get("bot") or {}).get("scan_limit")),
            "scan_deep_analysis_limit": ((settings.get("bot") or {}).get("scan_deep_analysis_limit")),
            "coin_filter": deepcopy(settings.get("coin_filter") or {}),
        },
    }


def _paper_lab_summary(username: str, period: dict[str, Any]) -> dict[str, Any]:
    runs = list_paper_lab_runs(username, limit=20)
    if not runs:
        latest_any = get_latest_paper_lab_run_any_user()
        runs = [latest_any] if latest_any else []

    return {
        "latest_run": runs[-1] if runs else {},
        "run_count": len(runs),
        "period_started_at": period["started_at"],
        "period_ended_at": period["ended_at"],
        "source": "paper_lab_store",
    }


def generate_eight_hour_report(username: str, data: dict[str, Any], settings: dict[str, Any], force: bool = False) -> dict[str, Any]:
    period = _last_completed_period()
    store = _read_store()
    cache_key = period["period_key"]
    reports = store.setdefault("reports", {})

    if not force and cache_key in reports:
        return deepcopy(reports[cache_key])

    bot_decision = build_bot_no_trade_reason_funnel(data, settings)
    report = {
        "status": "ok",
        "user": username,
        "period": period["period"],
        "period_key": cache_key,
        "period_date": period["period_date"],
        "timezone": EIGHT_HOUR_REPORT_TIMEZONE,
        "started_at": period["started_at"],
        "ended_at": period["ended_at"],
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "paper_lab": _paper_lab_summary(username, period),
        "bot_decision": bot_decision,
        "coinfilter": {
            "passed": bot_decision["coinfilter_passed"],
            "rejected": bot_decision["coinfilter_rejected"],
            "settings": deepcopy(settings.get("coin_filter") or {}),
        },
        "no_trade_reasons": bot_decision["top_blockers"],
        "runtime_health": build_runtime_health(data, settings),
    }
    reports[cache_key] = report
    store["reports"] = dict(list(reports.items())[-90:])
    _write_store(store)
    return deepcopy(report)


def latest_eight_hour_report(username: str, data: dict[str, Any], settings: dict[str, Any]) -> dict[str, Any]:
    return generate_eight_hour_report(username, data, settings, force=False)


def history_eight_hour_reports(limit: int = 20) -> dict[str, Any]:
    store = _read_store()
    reports = list((store.get("reports") or {}).values())[-max(1, int(limit or 20)):]
    return {
        "status": "ok",
        "timezone": EIGHT_HOUR_REPORT_TIMEZONE,
        "periods": list(EIGHT_HOUR_REPORT_PERIODS),
        "count": len(reports),
        "reports": reports,
    }
