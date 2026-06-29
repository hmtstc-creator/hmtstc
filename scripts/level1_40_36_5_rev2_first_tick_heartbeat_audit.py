#!/usr/bin/env python3
from __future__ import annotations

import ast
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
BOT_SERVICE = BACKEND / "services" / "bot_service.py"
MAIN = BACKEND / "main.py"
LOOP_CONTROL = BACKEND / "infrastructure" / "runtime" / "bot_loop_control.py"
RUNTIME_TRUTH = BACKEND / "services" / "bot_runtime_truth_service.py"
ANALYSIS = BACKEND / "services" / "analysis_service.py"
UNIVERSE = BACKEND / "services" / "coin_universe_service.py"
MARKET = BACKEND / "services" / "market_service.py"
BOT_JS = ROOT / "frontend" / "js" / "app" / "bot.js"
COIN_FILTER_JS = ROOT / "frontend" / "js" / "pages" / "coinFilter.js"
PRIOR = {
    "40.36.3": ROOT / "docs" / "LEVEL1_40_36_3_BOT_LOOP_CPU_THROTTLE_AUDIT.json",
    "40.36.4": ROOT / "docs" / "LEVEL1_40_36_4_BOT_START_FIRST_TICK_TIMEOUT_AUDIT.json",
    "40.36.5": ROOT / "docs" / "LEVEL1_40_36_5_HARD_CANCEL_BOT_SCAN_WORKER_AUDIT.json",
}
JSON_OUT = ROOT / "docs" / "LEVEL1_40_36_5_REV2_FIRST_TICK_HEARTBEAT_AUDIT.json"
MD_OUT = ROOT / "docs" / "LEVEL1_40_36_5_REV2_FIRST_TICK_HEARTBEAT_AUDIT.md"


def _text(path: Path) -> str:
    if not path.exists():
        raise FileNotFoundError(f"Missing required input: {path.relative_to(ROOT)}")
    return path.read_text(encoding="utf-8")


def _function(path: Path, name: str) -> str:
    text = _text(path)
    tree = ast.parse(text, filename=str(path))
    node = next((item for item in tree.body if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)) and item.name == name), None)
    if node is None:
        return ""
    lines = text.splitlines()
    return "\n".join(lines[node.lineno - 1:node.end_lineno])


def _isolated_function(path: Path, name: str, namespace: dict[str, Any]):
    text = _text(path)
    tree = ast.parse(text, filename=str(path))
    node = next(item for item in tree.body if isinstance(item, ast.FunctionDef) and item.name == name)
    module = ast.Module(body=[node], type_ignores=[])
    ast.fix_missing_locations(module)
    exec(compile(module, str(path), "exec"), namespace)
    return namespace[name]


def _first_tick_probe() -> dict[str, Any]:
    calls = {"scan_market": 0, "paper_lab": 0}

    def forbidden_scan(*args, **kwargs):
        calls["scan_market"] += 1
        raise AssertionError("first tick must not scan")

    def forbidden_paper(*args, **kwargs):
        calls["paper_lab"] += 1
        raise AssertionError("first tick must not run Paper Lab")

    counter = {"value": 0}

    def now_iso():
        counter["value"] += 1
        return f"2026-06-14T12:00:0{counter['value']}+00:00"

    function = _isolated_function(BOT_SERVICE, "run_bot_first_tick_guarded", {
        "scan_market": forbidden_scan,
        "run_paper_lab_tick": forbidden_paper,
        "now_iso": now_iso,
        "append_log": lambda *args, **kwargs: None,
    })
    state = {
        "requested_running": True,
        "bot_running": False,
        "engine_status": "starting",
        "primary_runtime_problem": "waiting_first_tick",
        "tick_in_progress": True,
        "last_scan": {"status": "idle", "time": None, "candidates": [], "scan_rows": []},
    }
    result = function(state, {}, limit=100)
    return {
        "result_status": result.get("status"),
        "result_mode": result.get("mode"),
        "scan_market_calls": calls["scan_market"],
        "paper_lab_calls": calls["paper_lab"],
        "last_tick": state.get("last_tick"),
        "last_scan_time": state.get("last_scan_time"),
        "engine_status": state.get("engine_status"),
        "primary_runtime_problem": state.get("primary_runtime_problem"),
        "tick_in_progress": state.get("tick_in_progress"),
    }


def _volume_probe() -> dict[str, Any]:
    analysis_safe_float = _isolated_function(ANALYSIS, "_safe_float", {"math": __import__("math")})
    universe_safe_float = _isolated_function(UNIVERSE, "_safe_float", {})
    samples = ["10k", "10K", "10,000", "10000", "$10k", "10k USDT"]
    analysis_values = {item: analysis_safe_float(item) for item in samples}
    universe_values = {item: universe_safe_float(item) for item in samples}

    universe_source = _text(UNIVERSE)
    tree = ast.parse(universe_source, filename=str(UNIVERSE))
    required_names = {"tradability_guard", "build_coin_universe", "base_asset", "is_stable_pair", "is_leveraged_token", "_safe_int"}
    selected = [node for node in tree.body if isinstance(node, (ast.FunctionDef, ast.Assign)) and (not isinstance(node, ast.FunctionDef) or node.name in required_names)]
    module = ast.Module(body=selected, type_ignores=[])
    ast.fix_missing_locations(module)
    namespace: dict[str, Any] = {"_safe_float": universe_safe_float}
    exec(compile(module, str(UNIVERSE), "exec"), namespace)
    report = namespace["build_coin_universe"]([
        {"symbol": "AAAUSDT", "lastPrice": "1", "quoteVolume": "9999", "count": 5000},
        {"symbol": "BBBUSDT", "lastPrice": "1", "quoteVolume": "10001", "count": 5000},
    ], settings={"coin_filter": {"min_quote_volume": "10k", "min_trade_count": 1}}, strict=True)
    diagnostic = report.get("volume_rejection_diagnostics") or {}
    sample = (diagnostic.get("sample_low_quote_volume") or [{}])[0]
    return {
        "analysis_values": analysis_values,
        "universe_values": universe_values,
        "all_parse_to_10000": all(value == 10000 for value in analysis_values.values()) and all(value == 10000 for value in universe_values.values()),
        "effective_min_quote_volume": diagnostic.get("effective_min_quote_volume"),
        "low_quote_volume_count": diagnostic.get("low_quote_volume_count"),
        "sample_quote_volume": sample.get("quoteVolume_USDT_24h"),
    }


def build_report() -> dict[str, Any]:
    first_tick = _function(BOT_SERVICE, "run_bot_first_tick_guarded")
    main = _text(MAIN)
    loop_control = _text(LOOP_CONTROL)
    runtime_truth = _text(RUNTIME_TRUTH)
    bot_js = _text(BOT_JS)
    analysis = _text(ANALYSIS)
    universe = _text(UNIVERSE)
    market = _text(MARKET)
    coin_filter_js = _text(COIN_FILTER_JS)
    first_tick_probe = _first_tick_probe()
    volume_probe = _volume_probe()
    prior_statuses = {name: json.loads(_text(path)).get("status") for name, path in PRIOR.items()}

    checks = {
        "first_tick_scan_market_free": "scan_market" not in first_tick and first_tick_probe["scan_market_calls"] == 0,
        "first_tick_deep_analysis_free": "deep_analysis" not in first_tick,
        "first_tick_paper_lab_free": "run_paper_lab_tick" not in first_tick and first_tick_probe["paper_lab_calls"] == 0,
        "first_tick_writes_last_tick": 'data["last_tick"] = now' in first_tick and bool(first_tick_probe["last_tick"]),
        "first_tick_finally_unlocks": "finally:" in first_tick and 'data["tick_in_progress"] = False' in first_tick and first_tick_probe["tick_in_progress"] is False,
        "first_tick_ok_sets_running": first_tick_probe["result_status"] == "ok" and first_tick_probe["result_mode"] == "heartbeat_first_tick" and first_tick_probe["engine_status"] == "running",
        "first_tick_ok_clears_problem": first_tick_probe["primary_runtime_problem"] is None,
        "first_tick_initializes_scan_timestamp": bool(first_tick_probe["last_scan_time"]),
        "main_preserves_ok_running_state": 'if result.get("status") == "ok":' in main and 'data["engine_status"] = "running"' in main and 'data["primary_runtime_problem"] = None' in main,
        "restore_proof_uses_heartbeat_tick": "return _after(data.get(\"last_tick\"), restore_started_at)" in loop_control and "last_scan" not in _function(LOOP_CONTROL, "restore_first_tick_ok"),
        "runtime_truth_allows_startup_scan_grace": "startup_scan_grace" in runtime_truth and "scan_runtime_ready" in runtime_truth,
        "frontend_poll_retry_is_nonfatal": "Bot start sonrası status geçici okunamadı; yeniden denenecek." in bot_js and "app.checkFirstTickResult(pollAttempt + 1);" in bot_js and "console.error(\"Bot first tick status kontrol hatası" not in bot_js,
        "frontend_start_200_not_generic_failure": "if ((result || {}).ok === false)" in bot_js and "Bot açıldı. Durum doğrulanıyor." in bot_js,
        "volume_parse_10k_variants": volume_probe["all_parse_to_10000"],
        "volume_filter_uses_quote_volume": "quoteVolume" in market and "baseVolume" not in market and "quoteVolume_USDT_24h" in universe,
        "volume_diagnostic_effective_min_10000": volume_probe["effective_min_quote_volume"] == 10000,
        "volume_rejected_real_quote_volume_present": volume_probe["sample_quote_volume"] == 9999 and "quoteVolume_USDT_24h" in coin_filter_js,
        "analysis_diagnostic_basis_present": '"volume_check_basis": "quoteVolume_USDT_24h"' in analysis,
        "prior_40_36_3_to_40_36_5_ok": all(status == "ok" for status in prior_statuses.values()),
    }
    blockers = [f"{name}=false" for name, value in checks.items() if not value]
    return {
        "status": "blocker" if blockers else "ok",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        **checks,
        "first_tick_probe": first_tick_probe,
        "volume_probe": volume_probe,
        "prior_audit_statuses": prior_statuses,
        "blockers": blockers,
    }


def _yn(value: bool) -> str:
    return "evet" if value else "hayir"


def write_markdown(report: dict[str, Any]) -> None:
    lines = [
        "# Level1 40.36.5 Rev2 First Tick Heartbeat Audit", "", "## Ozet", "",
        f"- Durum: `{report['status']}`",
        f"- Pure heartbeat first tick: `{_yn(report['first_tick_scan_market_free'] and report['first_tick_paper_lab_free'])}`",
        f"- Tick state running: `{_yn(report['first_tick_ok_sets_running'])}`",
        f"- Volume parse 10k: `{_yn(report['volume_parse_10k_variants'])}`",
        f"- Effective min quote volume: `{report['volume_probe']['effective_min_quote_volume']}`",
        "", "## Kontroller", "",
    ]
    for key, value in report.items():
        if isinstance(value, bool):
            lines.append(f"- {key}: `{_yn(value)}`")
    lines.extend(["", "## Blocker Listesi", ""])
    lines.extend(f"- BLOCKER: {item}" for item in report["blockers"]) if report["blockers"] else lines.append("Blocker yok.")
    lines.extend(["", "## Sonuc", ""])
    lines.append("Pure heartbeat first tick ve quote volume diagnostic kalite kapisi temiz." if report["status"] == "ok" else "Revize 2 first tick heartbeat kalite kapisi blocker durumunda.")
    lines.append("")
    MD_OUT.write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    try:
        report = build_report()
        JSON_OUT.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        write_markdown(report)
    except Exception as exc:
        print(f"LEVEL1_40_36_5_REV2_FIRST_TICK_HEARTBEAT_AUDIT_ERROR: {exc}", file=sys.stderr)
        return 1
    marker = "LEVEL1_40_36_5_REV2_FIRST_TICK_HEARTBEAT_AUDIT_OK" if report["status"] == "ok" else "LEVEL1_40_36_5_REV2_FIRST_TICK_HEARTBEAT_AUDIT_BLOCKER"
    print(marker)
    print(f"status={report['status']}")
    print(f"first_tick_scan_market_free={str(report['first_tick_scan_market_free']).lower()}")
    print(f"first_tick_ok_sets_running={str(report['first_tick_ok_sets_running']).lower()}")
    print(f"volume_parse_10k_variants={str(report['volume_parse_10k_variants']).lower()}")
    print(f"volume_diagnostic_effective_min_10000={str(report['volume_diagnostic_effective_min_10000']).lower()}")
    print(f"json={JSON_OUT.relative_to(ROOT)}")
    print(f"markdown={MD_OUT.relative_to(ROOT)}")
    return 1 if report["status"] == "blocker" else 0


if __name__ == "__main__":
    raise SystemExit(main())
