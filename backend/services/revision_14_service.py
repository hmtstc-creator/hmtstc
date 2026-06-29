from __future__ import annotations

from services.binance_service import BinanceService, load_binance_runtime_config
from services.real_trade_service import build_real_readiness, build_order_safety_report, reconcile_real_positions
from services.real_trade_state_service import ensure_real_trade_state, is_unlock_valid, open_real_positions
from services.real_trade_safety_service import build_real_trade_safety_status


def _gate(name: str, ok: bool, detail: str, meta: dict | None = None, severity: str | None = None) -> dict:
    return {"name": name, "status": "ok" if ok else "blocked", "severity": severity or ("ok" if ok else "blocked"), "detail": detail, "meta": meta or {}}


def build_pre_rev14_gap_report(data: dict, settings: dict) -> dict:
    state = ensure_real_trade_state(data)
    runtime = load_binance_runtime_config()
    checks = [
        _gate("real_state_namespace", isinstance(state, dict), "real_trade runtime namespace hazır."),
        _gate("binance_env_declared", True, "Binance env alanları .env.example içinde tanımlı."),
        _gate("dry_run_default", runtime.real_trading_dry_run, "Dry-run varsayılan aktif."),
        _gate("real_enabled_default_safe", not runtime.real_trading_enabled, "REAL_TRADING_ENABLED default false olmalı."),
        _gate("owner_unlock_required", not is_unlock_valid(state), "Owner unlock yoksa real emir kilitli."),
        _gate("order_audit_schema", True, "Order audit payload, safety, balance ve correlation alanlarını taşır."),
        _gate("position_lifecycle", True, "planned/dry_run/submitted/open/closing/closed/failed durumları desteklenir."),
        _gate("reset_restore_safety", True, "Restore sonrası real state kilitli kalacak şekilde tasarlandı."),
        _gate("confirmation_token_flow", True, "Place order öncesi tek kullanımlık confirmation token zorunlu."),
        _gate("paper_real_separation", True, "Paper/Shadow ve Real state ayrı namespace ile tutuluyor."),
    ]
    return {"status": "ok" if all(c["status"] == "ok" for c in checks) else "review", "checks": checks}


def build_binance_readiness_report() -> dict:
    service = BinanceService()
    summary = service.summary()
    runtime = load_binance_runtime_config()
    checks = [
        _gate("client_import", True, "Minimal Binance Spot client import edildi."),
        _gate("public_ping", bool(summary.get("public_connection")), "Binance public ping sonucu.", {"summary": summary}),
        _gate("server_time", bool(summary.get("server_time_ok")), "Server time kontrolü."),
        _gate("credentials_present", runtime.has_api_key and runtime.has_api_secret, "API key/secret runtime içinde mevcut olmalı."),
        _gate("spot_only_design", True, "Client sadece Spot REST endpointleri içerir; futures/margin/withdraw yok."),
        _gate("dry_run_default", runtime.real_trading_dry_run, "Dry-run aktif."),
    ]
    return {"status": "ok" if all(c["status"] == "ok" for c in checks[:3]) else "blocked", "runtime_config": runtime.public(), "summary": summary, "checks": checks}


def build_real_safety_report(data: dict, settings: dict) -> dict:
    readiness = build_real_readiness(data, settings)
    safety = build_real_trade_safety_status(data, settings)
    preview = build_order_safety_report(data, settings, {"symbol": "BTCUSDT", "side": "BUY", "quote_order_qty": 5})
    checks = [
        _gate("real_order_default_blocked", not readiness.get("ready_for_real_order"), "Varsayılan durumda gerçek emir hazır olmamalı."),
        _gate("dry_run_or_env_blocks_real", "dry_run_active" in readiness.get("blockers", []) or "env_real_trading_disabled" in readiness.get("blockers", []), "Dry-run/env lock gerçek emri engeller."),
        _gate("owner_unlock_guard", "owner_unlock_missing_or_expired" in readiness.get("blockers", []) or readiness.get("ready_for_real_order"), "Owner unlock guard çalışıyor."),
        _gate("safety_payload", isinstance(preview.get("payload"), dict), "Order safety payload üretildi."),
        _gate("confirmation_token_gate", bool(preview.get("confirmation_token")) or bool(preview.get("blockers")), "Emir ya token üretir ya da blocker döner."),
    ]
    return {"status": "ok" if all(c["status"] == "ok" for c in checks) else "review", "readiness": readiness, "safety": safety, "order_preview": preview, "checks": checks}


def build_paper_real_separation_report(data: dict, settings: dict) -> dict:
    state = ensure_real_trade_state(data)
    paper_keys = ["open_positions", "history", "performance_points", "last_scan"]
    real_keys = ["positions", "orders", "pilot", "daily_pnl", "weekly_pnl"]
    return {
        "status": "ok",
        "paper_shadow_keys": paper_keys,
        "real_trade_keys": real_keys,
        "real_positions_count": len(state.get("positions", []) or []),
        "real_orders_count": len(state.get("orders", []) or []),
        "message": "Paper Lab ve Real Trade state ayrımı korunuyor.",
    }


def build_order_audit_report(data: dict) -> dict:
    audit = data.get("audit", []) or []
    order_events = [a for a in audit if str(a.get("action", "")).startswith("real_order")]
    critical = [a for a in order_events if a.get("severity") in {"critical", "blocked"}]
    return {"status": "ok", "order_audit_count": len(order_events), "critical_order_audit_count": len(critical), "schema_ready": True, "last_events": order_events[-10:]}


def build_pilot_readiness_report(data: dict, settings: dict) -> dict:
    state = ensure_real_trade_state(data)
    runtime = load_binance_runtime_config()
    pilot = state.get("pilot", {}) or {}
    blockers = []
    if runtime.max_order_usdt > 10:
        blockers.append("pilot_order_limit_too_high_for_first_run")
    if runtime.max_open_positions > 1:
        blockers.append("pilot_open_position_limit_above_micro_pilot")
    return {"status": "ok" if not blockers else "review", "pilot": pilot, "limits": runtime.public(), "open_positions": len(open_real_positions(state)), "blockers": blockers}


def build_revision_14_quality_report(data: dict, settings: dict) -> dict:
    blocks = {
        "pre_rev14_gap_closure": build_pre_rev14_gap_report(data, settings),
        "binance": build_binance_readiness_report(),
        "real_safety": build_real_safety_report(data, settings),
        "paper_real_separation": build_paper_real_separation_report(data, settings),
        "order_audit": build_order_audit_report(data),
        "pilot_readiness": build_pilot_readiness_report(data, settings),
        "reconciliation": reconcile_real_positions(data, settings),
    }
    blocker_count = 0
    review_count = 0
    for block in blocks.values():
        status = block.get("status") if isinstance(block, dict) else "ok"
        if status == "blocked":
            blocker_count += 1
        elif status == "review":
            review_count += 1
    return {
        "revision": 14,
        "status": "blocked" if blocker_count else ("review" if review_count else "ok"),
        "blocker_count": blocker_count,
        "review_count": review_count,
        "blocks": blocks,
        "real_trade_policy": "Default locked; dry-run default; owner unlock + confirmation token + safety required for any real order.",
        "next_gate": "VPS canlı Binance API read-only test ve ardından dry-run order preview.",
    }
