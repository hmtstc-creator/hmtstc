#!/usr/bin/env python3
from __future__ import annotations

import importlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
API_JS = ROOT / "frontend" / "js" / "app" / "api.js"
STATE_JS = ROOT / "frontend" / "js" / "app" / "state.js"
COIN_FILTER_JS = ROOT / "frontend" / "js" / "pages" / "coinFilter.js"
DASHBOARD_JS = ROOT / "frontend" / "js" / "pages" / "dashboard.js"
BOT_JS = ROOT / "frontend" / "js" / "app" / "bot.js"
ANALYSIS_SERVICE = BACKEND / "services" / "analysis_service.py"
BOT_SERVICE = BACKEND / "services" / "bot_service.py"
BOT_ROUTES = BACKEND / "routes" / "bot_routes.py"
BOT_TRUTH = BACKEND / "services" / "bot_runtime_truth_service.py"
LOOP_CONTROL = BACKEND / "infrastructure" / "runtime" / "bot_loop_control.py"
MAIN = BACKEND / "main.py"
JSON_OUT = ROOT / "docs" / "LEVEL1_40_36_BOT_START_AND_COINFILTER_SAVE_STABILITY_AUDIT.json"
MD_OUT = ROOT / "docs" / "LEVEL1_40_36_BOT_START_AND_COINFILTER_SAVE_STABILITY_AUDIT.md"
PRIOR_AUDITS = [
    ROOT / "docs" / f"LEVEL1_40_{number}_{name}_AUDIT.json"
    for number, name in [
        (20, "LIVE_STARTUP_RULES_HYDRATION"),
        (21, "AUTH_RESTORE_TRUTH"),
        (22, "COINFILTER_RULES_PAPERLAB"),
        (23, "RULES_PAPERLAB_INDEPENDENCE"),
        (24, "PAPERLAB_AUTONOMOUS_ENGINE"),
        (25, "PAPERLAB_PERSISTENCE"),
        (26, "PAPERLAB_HYDRATION_STABILITY"),
        (27, "RUNTIME_HEALTH_PAPERLAB_STORE"),
        (28, "RUNTIME_HEALTH_PAPERLAB_USER_RESOLUTION"),
        (29, "COINFILTER_PERSISTENCE_AND_8H_REPORT"),
        (30, "BOT_RUNTIME_HEARTBEAT_TRUTH"),
        (31, "BOT_RESTORE_REAL_LOOP"),
        (32, "BOT_RESTORE_FIRST_TICK"),
        (33, "COINFILTER_FINAL_PIPELINE"),
        (34, "COINFILTER_TEST_SCAN_TIMEOUT"),
        (35, "LAST_SCAN_CONTRACT_PRESERVATION"),
    ]
]


def _load_text(path: Path) -> str:
    if not path.exists():
        raise FileNotFoundError(f"Missing required input: {path.relative_to(ROOT)}")
    return path.read_text(encoding="utf-8")


def _load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(f"Missing required input: {path.relative_to(ROOT)}")
    return json.loads(path.read_text(encoding="utf-8"))


def _section(text: str, start: str, end: str) -> str:
    start_index = text.find(start)
    if start_index < 0:
        return ""
    end_index = text.find(end, start_index + len(start))
    return text[start_index:] if end_index < 0 else text[start_index:end_index]


def _runtime_probe() -> dict[str, Any]:
    sys.path.insert(0, str(BACKEND))
    analysis = importlib.import_module("services.analysis_service")
    bot_service = importlib.import_module("services.bot_service")
    original_market = analysis.get_market_symbols

    settings = {
        "coin_filter": {
            "min_quote_volume": 1234567,
            "min_trade_count": 2345,
            "min_volatility": 0.7,
            "volatility_candle_count": 18,
            "volatility_interval": "1h",
            "rsi_min_15m": 41,
            "rsi_max_15m": 71,
            "rsi_min_1h": 42,
            "rsi_max_1h": 72,
            "rsi_min_4h": 43,
            "rsi_max_4h": 73,
            "volume_growth_multiplier": 1.4,
            "excluded_symbols": "XRPUSDT, BTCUSDT, XRPUSDT",
        },
        "bot": {"scan_deep_analysis_limit": 33},
    }

    def fake_market(*, limit: int, settings: dict, strict: bool) -> dict:
        return {
            "status": "ok",
            "live": True,
            "count": 1,
            "total_seen": 1,
            "universe_rejected_count": 0,
            "universe_rejection_breakdown": {},
            "symbols": [{
                "symbol": "ETHUSDT",
                "price": "3000",
                "high_price": "3030",
                "low_price": "2970",
                "quote_volume": 900000000,
                "trade_count": 500000,
                "change_percent": 1.0,
            }],
        }

    try:
        analysis.get_market_symbols = fake_market
        scan = analysis.scan_market(settings, limit=20, deep_analysis=False)
    finally:
        analysis.get_market_symbols = original_market

    bot_data: dict[str, Any] = {}
    bot_service.start_bot(bot_data, mode="paper")
    settings_used = (scan.get("scan_diagnostics") or {}).get("coin_filter_settings_used") or {}
    return {
        "settings_used": settings_used,
        "start_requested_running": bot_data.get("requested_running"),
        "start_bot_running": bot_data.get("bot_running"),
        "start_engine_status": bot_data.get("engine_status"),
        "start_primary_runtime_problem": bot_data.get("primary_runtime_problem"),
    }


def build_report() -> dict[str, Any]:
    api_js = _load_text(API_JS)
    state_js = _load_text(STATE_JS)
    coin_filter_js = _load_text(COIN_FILTER_JS)
    dashboard_js = _load_text(DASHBOARD_JS)
    bot_js = _load_text(BOT_JS)
    analysis_service = _load_text(ANALYSIS_SERVICE)
    bot_service = _load_text(BOT_SERVICE)
    bot_routes = _load_text(BOT_ROUTES)
    bot_truth = _load_text(BOT_TRUTH)
    loop_control = _load_text(LOOP_CONTROL)
    main_py = _load_text(MAIN)
    save_fn = _section(coin_filter_js, "save: async function", "fetchLastScan: async function")
    start_fn = _section(bot_routes, "def bot_start", '@router.post("/stop")')
    stop_fn = _section(bot_routes, "def bot_stop", '@router.post("/emergency-stop")')
    probe = _runtime_probe()
    prior_statuses = {path.stem: _load_json(path).get("status") for path in PRIOR_AUDITS}
    settings_used = probe["settings_used"]
    required_settings = [
        "min_quote_volume", "min_trade_count", "min_volatility", "volatility_candle_count",
        "volatility_interval", "rsi_min_15m", "rsi_max_15m", "rsi_min_1h",
        "rsi_max_1h", "rsi_min_4h", "rsi_max_4h", "volume_growth_multiplier",
        "excluded_symbols", "scan_deep_analysis_limit",
    ]
    all_runtime_text = bot_service + bot_routes + bot_truth + loop_control + main_py
    checks = {
        "coinfilter_save_abort_error_guarded": all(value in api_js for value in ["timedOut", 'type = timedOut ? "timeout"', 'controller.abort("hmtstc_request_timeout")']),
        "coinfilter_save_polling_abort_isolated": save_fn.count("preventGlobalAbort: true") >= 2 and 'if (HMTSTC_APP.state.coinFilterSaving)' in save_fn,
        "coinfilter_save_backend_reload_present": save_fn.count('fetchJson("/api/settings"') >= 2 and "refreshMatches" in save_fn,
        "coinfilter_save_ui_states_present": all(value in coin_filter_js + state_js for value in ["Kaydediliyor...", "Başarıyla kaydedildi", "Kaydetme başarısız:", "coinFilterSaveStatus"]),
        "coinfilter_required_settings_preserved": all(key in settings_used for key in required_settings),
        "coinfilter_min_quote_volume_preserved": settings_used.get("min_quote_volume") == 1234567,
        "coinfilter_min_trade_count_preserved": settings_used.get("min_trade_count") == 2345,
        "coinfilter_excluded_symbols_normalized": settings_used.get("excluded_symbols") == ["BTCUSDT", "XRPUSDT"],
        "scan_diagnostics_settings_used_present": '"coin_filter_settings_used"' in analysis_service,
        "bot_start_requested_running_true": probe["start_requested_running"] is True and '"requested_running": True' in start_fn,
        "bot_start_waits_for_first_tick": probe["start_bot_running"] is True and probe["start_engine_status"] == "running" and probe["start_primary_runtime_problem"] is None,
        "bot_start_resets_first_tick_proof": 'data["last_runtime_restore_first_tick_ok_at"] = now' in bot_service and 'data["last_runtime_restore_at"] = now' in bot_service,
        "bot_stop_user_requested_contract": 'reason="user_requested_stop"' in stop_fn and '"requested_running": False' in stop_fn,
        "restore_failure_preserves_requested_running": 'data["requested_running"] = False' in loop_control and 'data["tick_in_progress"] = False' in loop_control,
        "bot_status_primary_runtime_problem_present": '"primary_runtime_problem": runtime_truth["primary_runtime_problem"]' in bot_routes,
        "bot_status_thread_alive_present": '"thread_alive": runtime_truth["thread_alive"]' in bot_routes and '"thread_alive": task_alive' in bot_truth,
        "bot_start_diagnostics_present": all(event in all_runtime_text for event in [
            "BOT_START_HEARTBEAT_ONLY_OK", "BOT_STOP_REQUESTED",
        ]),
        "dashboard_starting_failed_states_present": all(value in dashboard_js for value in ['"restoring"', '"failed"', '"stale"']),
        "frontend_bot_requested_state_present": all(value in bot_js for value in ["requested_running", "Bot başlatıldı. İlk piyasa taraması hazırlanıyor.", "primary_runtime_problem", 'requestKind: "mutation"']),
        "previous_40_20_to_40_35_status_ok": all(status == "ok" for status in prior_statuses.values()),
    }
    blockers = [f"{name}=false" for name, value in checks.items() if not value]
    return {
        "status": "blocker" if blockers else "ok",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        **checks,
        "runtime_probe": probe,
        "prior_statuses": prior_statuses,
        "blockers": blockers,
        "recommended_next_actions": [
            "Canli ortamda CoinFilter save, Ctrl+F5 ve backend settings echo zincirini dogrula.",
            "Bot start sonrasi requested_running=true kalirken loop/tick sonucunu status endpointinden izle.",
            "Paket 10.22'yi yalnizca Paket 10.21 canli kabul tamamlandiktan sonra baslat.",
        ],
    }


def _yn(value: bool) -> str:
    return "evet" if value else "hayir"


def write_markdown(report: dict[str, Any]) -> None:
    lines = [
        "# Level1 40.36 Bot Start and CoinFilter Save Stability Audit",
        "",
        "## Ozet",
        "",
        f"- Durum: `{report['status']}`",
        f"- CoinFilter save isolation: `{_yn(report['coinfilter_save_polling_abort_isolated'])}`",
        f"- Settings used contract: `{_yn(report['scan_diagnostics_settings_used_present'])}`",
        f"- Bot requested running korunuyor: `{_yn(report['bot_start_requested_running_true'])}`",
        f"- Onceki 40.20-40.35 zinciri: `{_yn(report['previous_40_20_to_40_35_status_ok'])}`",
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
    lines.append("Bot start ve CoinFilter save stability kalite kapisi temiz." if report["status"] == "ok" else "Bot start veya CoinFilter save stability blocker durumunda.")
    lines.append("")
    MD_OUT.write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    try:
        report = build_report()
        JSON_OUT.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        write_markdown(report)
    except Exception as exc:
        print(f"LEVEL1_40_36_BOT_START_AND_COINFILTER_SAVE_STABILITY_AUDIT_ERROR: {exc}", file=sys.stderr)
        return 1

    marker = {
        "ok": "LEVEL1_40_36_BOT_START_AND_COINFILTER_SAVE_STABILITY_AUDIT_OK",
        "blocker": "LEVEL1_40_36_BOT_START_AND_COINFILTER_SAVE_STABILITY_AUDIT_BLOCKER",
    }[report["status"]]
    print(marker)
    print(f"status={report['status']}")
    print(f"coinfilter_save_polling_abort_isolated={str(report['coinfilter_save_polling_abort_isolated']).lower()}")
    print(f"scan_diagnostics_settings_used_present={str(report['scan_diagnostics_settings_used_present']).lower()}")
    print(f"bot_start_requested_running_true={str(report['bot_start_requested_running_true']).lower()}")
    print(f"previous_40_20_to_40_35_status_ok={str(report['previous_40_20_to_40_35_status_ok']).lower()}")
    print(f"json={JSON_OUT.relative_to(ROOT)}")
    print(f"markdown={MD_OUT.relative_to(ROOT)}")
    return 1 if report["status"] == "blocker" else 0


if __name__ == "__main__":
    raise SystemExit(main())
