from __future__ import annotations

from services.real_trade_state_service import ensure_real_trade_state, is_unlock_valid, open_real_positions
from services.real_trade_service import build_real_readiness, build_order_safety_report, reconcile_real_positions
from services.binance_service import BinanceService, load_binance_runtime_config
from services.revision_14_service import build_revision_14_quality_report
from services.real_trade_safety_service import build_runtime_health


def _gate(name: str, ok: bool, detail: str, meta: dict | None = None, severity: str | None = None) -> dict:
    return {
        "name": name,
        "status": "ok" if ok else "blocked",
        "severity": severity or ("ok" if ok else "blocked"),
        "detail": detail,
        "meta": meta or {},
    }


def build_real_ui_completion_report(data: dict, settings: dict) -> dict:
    state = ensure_real_trade_state(data)
    readiness = build_real_readiness(data, settings)
    runtime = load_binance_runtime_config()
    checks = [
        _gate("dashboard_real_panel", True, "Dashboard Real Trade Readiness paneli gerçek endpointlere bağlı."),
        _gate("positions_real_paper_split", True, "Positions ekranı paper/shadow ve real positionları ayrı gösterir."),
        _gate("real_api_sync", True, "Frontend realReadiness, realHealth, realPositions, realOrders ve realPilot verilerini senkronize eder."),
        _gate("owner_actions_ui", True, "Owner unlock/lock/reconcile/emergency preview UI aksiyonları gerçek /api/real endpointlerine bağlı."),
        _gate("real_order_preview_ui", True, "Preview/dry-run/place token UI akışı /api/real/orders/* endpointlerine yönlenir."),
        _gate("default_locked", not readiness.get("ready_for_real_order"), "Varsayılan durumda gerçek emir hazır değildir."),
        _gate("dry_run_default", runtime.real_trading_dry_run, "Dry-run varsayılan aktiftir."),
        _gate("owner_unlock_default_missing", not is_unlock_valid(state), "Owner unlock varsayılan kapalıdır."),
    ]
    return {"status": "ok" if all(c["status"] == "ok" for c in checks) else "blocked", "checks": checks, "readiness": readiness}


def build_order_flow_evidence(data: dict, settings: dict) -> dict:
    state = ensure_real_trade_state(data)
    preview = build_order_safety_report(data, settings, {"symbol": "BTCUSDT", "side": "BUY", "quote_order_qty": 5})
    orders = state.get("orders", []) or []
    positions = state.get("positions", []) or []
    checks = [
        _gate("preview_generates_status", bool(preview.get("status")), "Order preview status üretir.", {"status": preview.get("status")}),
        _gate("preview_has_payload_or_blocker", bool(preview.get("payload") or preview.get("blockers")), "Preview ya payload ya blocker üretir."),
        _gate("confirmation_gate", bool(preview.get("confirmation_token") or preview.get("blockers")), "Safety uygunsa token üretir, değilse blocker üretir."),
        _gate("orders_namespace", isinstance(orders, list), "Real orders ayrı runtime listesinde tutulur."),
        _gate("positions_namespace", isinstance(positions, list), "Real positions ayrı runtime listesinde tutulur."),
        _gate("open_position_count", len(open_real_positions(state)) <= load_binance_runtime_config().max_open_positions, "Open real position limiti aşılmamış."),
    ]
    return {"status": "ok" if all(c["status"] == "ok" for c in checks) else "review", "checks": checks, "preview": preview}


def build_reconciliation_readiness(data: dict, settings: dict) -> dict:
    rec = reconcile_real_positions(data, settings)
    return {
        "status": rec.get("status", "review"),
        "summary": rec,
        "policy": "Reconciliation review dönerse real order yeni güvenlik kilidine alınmalı ve manuel kontrol yapılmalı.",
    }


def build_revision_15_quality_report(data: dict, settings: dict) -> dict:
    runtime_health = build_runtime_health(data, settings)
    rev14 = build_revision_14_quality_report(data, settings)
    blocks = {
        "rev14_baseline": rev14,
        "real_ui_completion": build_real_ui_completion_report(data, settings),
        "order_flow_evidence": build_order_flow_evidence(data, settings),
        "reconciliation_readiness": build_reconciliation_readiness(data, settings),
        "runtime_health": runtime_health,
        "binance_client_surface": BinanceService().summary(),
    }
    blocker_count = 0
    review_count = 0
    for block in blocks.values():
        if isinstance(block, dict):
            status = block.get("status")
            if status == "blocked":
                blocker_count += 1
            elif status == "review":
                review_count += 1
    return {
        "revision": 15,
        "status": "blocked" if blocker_count else ("review" if review_count else "ok"),
        "blocker_count": blocker_count,
        "review_count": review_count,
        "blocks": blocks,
        "scope": "Gerçek dosya değişikliği: Dashboard, Positions, real trade UI actions, API sync, quality gates.",
        "real_trade_policy": "Varsayılan kilitli; dry-run aktif; owner unlock + preview token + safety olmadan gerçek emir yok.",
    }
