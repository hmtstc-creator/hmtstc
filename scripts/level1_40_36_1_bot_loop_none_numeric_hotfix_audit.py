#!/usr/bin/env python3
from __future__ import annotations

import importlib
import json
import math
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
ANALYSIS_SERVICE = BACKEND / "services" / "analysis_service.py"
BOT_SERVICE = BACKEND / "services" / "bot_service.py"
BOT_TRUTH = BACKEND / "services" / "bot_runtime_truth_service.py"
PAPER_LAB = BACKEND / "services" / "paper_lab_service.py"
POSITION_SERVICE = BACKEND / "services" / "position_service.py"
LOOP_CONTROL = BACKEND / "infrastructure" / "runtime" / "bot_loop_control.py"
MAIN = BACKEND / "main.py"
PRIOR_AUDIT = ROOT / "docs" / "LEVEL1_40_36_BOT_START_AND_COINFILTER_SAVE_STABILITY_AUDIT.json"
JSON_OUT = ROOT / "docs" / "LEVEL1_40_36_1_BOT_LOOP_NONE_NUMERIC_HOTFIX_AUDIT.json"
MD_OUT = ROOT / "docs" / "LEVEL1_40_36_1_BOT_LOOP_NONE_NUMERIC_HOTFIX_AUDIT.md"


def _load_text(path: Path) -> str:
    if not path.exists():
        raise FileNotFoundError(f"Missing required input: {path.relative_to(ROOT)}")
    return path.read_text(encoding="utf-8")


def _load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(f"Missing required input: {path.relative_to(ROOT)}")
    return json.loads(path.read_text(encoding="utf-8"))


def _valid_kline(price: float = 100.0, volume: float = 1_000_000.0) -> list[Any]:
    return [0, str(price), str(price + 1), str(price - 1), str(price), "0", 0, str(volume)]


def _runtime_probe() -> dict[str, Any]:
    sys.path.insert(0, str(BACKEND))
    service = importlib.import_module("services.analysis_service")
    originals = {
        "fetch_klines": service.fetch_klines,
        "rsi": service.rsi,
        "get_market_symbols": service.get_market_symbols,
    }
    settings = {"bot": {"scan_deep_analysis_limit": 80}}

    def null_kline_fetch(symbol: str, interval: str, limit: int) -> list[list[Any]]:
        rows = [_valid_kline() for _ in range(max(limit, 20))]
        rows[-1][4] = None
        return rows

    try:
        service.fetch_klines = null_kline_fetch
        null_kline_result = service.analyze_symbol("BTCUSDT", settings)

        service.fetch_klines = lambda symbol, interval, limit: [_valid_kline() for _ in range(max(limit, 20))]
        service.rsi = lambda values, period=14: None
        null_indicator_result = service.analyze_symbol("ETHUSDT", settings)

        service.rsi = originals["rsi"]
        service.get_market_symbols = lambda **kwargs: {
            "status": "ok",
            "live": True,
            "count": 1,
            "total_seen": 1,
            "universe_rejected_count": 0,
            "universe_rejection_breakdown": {},
            "symbols": [{
                "symbol": "NULLUSDT",
                "price": None,
                "high_price": None,
                "low_price": None,
                "quote_volume": None,
                "trade_count": None,
                "change_percent": None,
                "weighted_avg_price": None,
            }],
        }
        market_result = service.scan_market(settings, limit=20, deep_analysis=False)
    finally:
        service.fetch_klines = originals["fetch_klines"]
        service.rsi = originals["rsi"]
        service.get_market_symbols = originals["get_market_symbols"]

    market_row = (market_result.get("scan_rows") or [{}])[0]
    return {
        "null_kline_passed": null_kline_result.get("passed"),
        "null_kline_reason": null_kline_result.get("reason"),
        "null_indicator_passed": null_indicator_result.get("passed"),
        "null_indicator_reason": null_indicator_result.get("reason"),
        "market_status": market_result.get("status"),
        "market_candidates_count": market_result.get("candidates_count"),
        "market_row_status": market_row.get("status"),
        "market_row_price": market_row.get("price"),
        "market_row_quote_volume": market_row.get("quote_volume"),
        "market_row_trade_count": market_row.get("trade_count"),
        "market_row_score": market_row.get("score"),
    }


def build_report() -> dict[str, Any]:
    analysis_text = _load_text(ANALYSIS_SERVICE)
    bot_text = _load_text(BOT_SERVICE)
    truth_text = _load_text(BOT_TRUTH)
    paper_lab_text = _load_text(PAPER_LAB)
    position_text = _load_text(POSITION_SERVICE)
    loop_text = _load_text(LOOP_CONTROL)
    main_text = _load_text(MAIN)
    prior_status = _load_json(PRIOR_AUDIT).get("status")
    probe = _runtime_probe()

    checks = {
        "analysis_safe_float_finite_guard_present": "math.isfinite" in analysis_text and "def _finite_float" in analysis_text,
        "kline_numeric_series_guard_present": "def _numeric_series" in analysis_text and "invalid_numeric_indicator" in analysis_text,
        "null_kline_rejected_without_crash": probe["null_kline_passed"] is False and probe["null_kline_reason"] == "invalid_numeric_indicator",
        "null_indicator_rejected_without_crash": probe["null_indicator_passed"] is False and probe["null_indicator_reason"] == "invalid_numeric_indicator",
        "null_market_values_rejected_without_crash": probe["market_status"] == "ok" and probe["market_candidates_count"] == 0 and probe["market_row_status"] == "REJECT",
        "scan_rows_numeric_contract_present": all(
            isinstance(probe[key], (int, float)) and math.isfinite(float(probe[key]))
            for key in ["market_row_price", "market_row_quote_volume", "market_row_trade_count", "market_row_score"]
        ),
        "bot_candidate_numeric_guard_present": "def _safe_float" in bot_text and '_safe_float(candidate.get("price"), 0.0)' in bot_text and "_safe_float(get_position_size" in bot_text,
        "paper_lab_score_comparisons_safe": all(value in paper_lab_text for value in [
            '_safe_float(row.get("stability_score")) >= 55',
            '_safe_float(row.get("execution_quality_score")) >= 45',
            'abs(_safe_float(row.get("max_drawdown_percent"))) <= 8',
        ]),
        "position_current_price_comparison_safe": '_safe_float(get_current_price(symbol' in position_text and '"invalid_current_price"' in position_text,
        "deep_analysis_runtime_cap_present": 'min(_safe_int(bot_settings.get("scan_deep_analysis_limit"), 8), 8)' in analysis_text,
        "bot_loop_traceback_logging_present": "traceback.format_exc" in main_text and "last_runtime_traceback" in main_text and "traceback={trace_text}" in main_text,
        "bot_loop_user_error_preserves_requested_running": 'data["requested_running"] = False' in main_text and 'mark_user_bot_requested(user, False)' in main_text,
        "bot_loop_user_error_does_not_kill_global_task": "mark_bot_task_exception(user_error, user)" not in main_text and "mark_bot_task_heartbeat(user)" in main_text,
        "runtime_truth_preserves_real_problem": "stored_problem" in truth_text and "bot_loop_task_failed:{task_exception}" in truth_text,
        "restore_failure_preserves_requested_running": 'data["requested_running"] = False' in loop_text and 'data["tick_in_progress"] = False' in loop_text,
        "prior_40_36_status_ok": prior_status == "ok",
    }
    blockers = [f"{key}=false" for key, value in checks.items() if not value]
    return {
        "status": "blocker" if blockers else "ok",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        **checks,
        "runtime_probe": probe,
        "prior_40_36_status": prior_status,
        "blockers": blockers,
        "recommended_next_actions": [
            "Deploy sonrasi bot loop loglarinda NoneType numeric comparison hatasi olmadigini izle.",
            "Rejected coinlerde invalid_numeric_indicator veya missing_numeric_indicator nedenini dogrula.",
            "Bot status icinde requested_running=true ve gercek primary_runtime_problem contract'ini kontrol et.",
        ],
    }


def _yn(value: bool) -> str:
    return "evet" if value else "hayir"


def write_markdown(report: dict[str, Any]) -> None:
    lines = [
        "# Level1 40.36.1 Bot Loop None Numeric Hotfix Audit",
        "",
        "## Ozet",
        "",
        f"- Durum: `{report['status']}`",
        f"- None kline reject: `{_yn(report['null_kline_rejected_without_crash'])}`",
        f"- None indicator reject: `{_yn(report['null_indicator_rejected_without_crash'])}`",
        f"- Loop traceback logging: `{_yn(report['bot_loop_traceback_logging_present'])}`",
        f"- 40.36 status: `{report['prior_40_36_status']}`",
        "",
        "## Kontroller",
        "",
    ]
    for key, value in report.items():
        if isinstance(value, bool):
            lines.append(f"- {key}: `{_yn(value)}`")
    lines.extend(["", "## Blocker Listesi", ""])
    if report["blockers"]:
        lines.extend(f"- BLOCKER: {blocker}" for blocker in report["blockers"])
    else:
        lines.append("Blocker yok.")
    lines.extend(["", "## Sonuc", ""])
    lines.append("Bot loop None numeric hotfix kalite kapisi temiz." if report["status"] == "ok" else "Bot loop None numeric hotfix blocker durumunda.")
    lines.append("")
    MD_OUT.write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    try:
        report = build_report()
        JSON_OUT.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        write_markdown(report)
    except Exception as exc:
        print(f"LEVEL1_40_36_1_BOT_LOOP_NONE_NUMERIC_HOTFIX_AUDIT_ERROR: {exc}", file=sys.stderr)
        return 1

    marker = {
        "ok": "LEVEL1_40_36_1_BOT_LOOP_NONE_NUMERIC_HOTFIX_AUDIT_OK",
        "blocker": "LEVEL1_40_36_1_BOT_LOOP_NONE_NUMERIC_HOTFIX_AUDIT_BLOCKER",
    }[report["status"]]
    print(marker)
    print(f"status={report['status']}")
    print(f"null_kline_rejected_without_crash={str(report['null_kline_rejected_without_crash']).lower()}")
    print(f"null_indicator_rejected_without_crash={str(report['null_indicator_rejected_without_crash']).lower()}")
    print(f"bot_loop_traceback_logging_present={str(report['bot_loop_traceback_logging_present']).lower()}")
    print(f"prior_40_36_status={report['prior_40_36_status']}")
    print(f"json={JSON_OUT.relative_to(ROOT)}")
    print(f"markdown={MD_OUT.relative_to(ROOT)}")
    return 1 if report["status"] == "blocker" else 0


if __name__ == "__main__":
    raise SystemExit(main())
