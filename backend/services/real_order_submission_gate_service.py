from __future__ import annotations

from typing import Any

from core.storage import now_iso
from services.binance_service import load_binance_runtime_config
from services.strategy_filter_toggle_service import get_strategy_filter_toggles


def _safe_float(value: Any, fallback: float = 0.0) -> float:
    try:
        if isinstance(value, str):
            value = value.replace("USDT", "").replace(",", ".").strip()
        return float(value)
    except Exception:
        return fallback


def normalize_real_order_request(order: dict | None) -> dict:
    raw = order or {}
    meta = raw.get("meta") if isinstance(raw.get("meta"), dict) else {}
    quote_order_qty = _safe_float(
        raw.get("quote_order_qty", raw.get("quote_amount", raw.get("usdt_size", meta.get("quote_order_qty", meta.get("quote_amount", 0))))),
        0.0,
    )
    return {
        "symbol": str(raw.get("symbol") or meta.get("symbol") or "").upper().strip(),
        "side": str(raw.get("side") or meta.get("side") or "BUY").upper().strip(),
        "quote_order_qty": quote_order_qty,
        "preview_id": str(raw.get("preview_id") or meta.get("preview_id") or "").strip(),
        "confirmation_token": str(raw.get("confirmation_token") or raw.get("preview_token") or meta.get("confirmation_token") or "").strip(),
        "owner_confirmed": bool(raw.get("owner_confirmed") or meta.get("owner_confirmed")),
        "final_ack": str(raw.get("final_ack") or meta.get("final_ack") or "").strip(),
    }


_PLAIN_BLOCKERS = {
    "owner_role_required": "Gerçek emir sadece owner tarafından gönderilebilir.",
    "owner_confirmed_missing": "Gerçek para için son onay kutusu işaretlenmedi.",
    "final_ack_missing": "Gerçek para metin onayı eksik.",
    "live_readiness_blocked": "Canlı işlem hazırlığı geçmedi.",
    "dry_run_not_passed": "Emir denemesi güvenli sonucu vermedi.",
    "real_trading_not_enabled": "Gerçek para modu açık değil.",
    "dry_run_mode_active": "Sistem hâlâ prova modunda.",
    "strategy_filter_missing": "Açık strateji veya filtre seçimi eksik.",
}


def plain_blocker(code: str) -> str:
    return _PLAIN_BLOCKERS.get(code, str(code).replace("_", " "))


def build_real_order_submission_gate(
    data: dict,
    settings: dict,
    order: dict | None,
    *,
    user: str = "default",
    role: str = "owner",
    require_ack: bool = True,
) -> dict:
    """Final backend gate before any real order can be submitted.

    This function deliberately does not place orders. It aggregates the live readiness
    gate, dry-run simulation and explicit owner acknowledgement so frontend changes
    cannot bypass money-moving safeguards.
    """
    from services.live_trade_readiness_check_service import build_live_trade_readiness_check
    from services.real_order_dry_run_simulation_service import build_real_order_dry_run_simulation

    normalized = normalize_real_order_request(order)
    runtime = load_binance_runtime_config()
    readiness = build_live_trade_readiness_check(data, settings, user=user)
    dry_run = build_real_order_dry_run_simulation(data, settings, normalized, user=user, role=role)
    toggles = get_strategy_filter_toggles(user)

    blockers: list[str] = []
    if role != "owner":
        blockers.append("owner_role_required")
    if not readiness.get("ready_for_real_order"):
        blockers.append("live_readiness_blocked")
    if dry_run.get("status") != "ready":
        blockers.append("dry_run_not_passed")
    if not runtime.real_trading_enabled:
        blockers.append("real_trading_not_enabled")
    if runtime.real_trading_dry_run:
        blockers.append("dry_run_mode_active")
    if not (toggles.get("selected_strategy_ids") and toggles.get("selected_filter_ids")):
        blockers.append("strategy_filter_missing")
    if require_ack and not normalized.get("owner_confirmed"):
        blockers.append("owner_confirmed_missing")
    if require_ack and normalized.get("final_ack") != "GERCEK PARA":
        blockers.append("final_ack_missing")

    blockers.extend([str(x) for x in readiness.get("blockers") or []])
    blockers.extend([str(x) for x in dry_run.get("blockers") or []])
    blockers = sorted({str(x).strip() for x in blockers if str(x).strip()})
    status = "ready" if not blockers else "blocked"
    result = {
        "status": status,
        "simple_status": "Gerçek emir gönderilebilir" if status == "ready" else "Gerçek emir gönderilemez",
        "real_order_allowed": status == "ready",
        "real_order_created": False,
        "order": normalized,
        "blockers": blockers,
        "blocker_texts": [plain_blocker(item) for item in blockers],
        "readiness": {
            "simple_status": readiness.get("simple_status"),
            "ready_for_real_order": readiness.get("ready_for_real_order"),
            "ready_for_dry_run": readiness.get("ready_for_dry_run"),
        },
        "dry_run": {
            "status": dry_run.get("status"),
            "simple_status": dry_run.get("simple_status"),
            "dry_run_only": dry_run.get("dry_run_only"),
            "real_order_created": dry_run.get("real_order_created"),
        },
        "runtime": {
            "real_trading_enabled": bool(runtime.real_trading_enabled),
            "dry_run": bool(runtime.real_trading_dry_run),
            "testnet": bool(runtime.testnet),
            "mode": runtime.mode,
        },
        "checked_at": now_iso(),
    }
    data.setdefault("real_trade", {})["last_order_submission_gate"] = result
    return result


def build_real_order_submission_gate_quality_report() -> dict:
    sample_data = {"wallet_value": 1000}
    sample_settings = {"bot": {"usdt_per_position": 10, "max_open_positions": 1}, "risk": {"daily_loss_limit": "30 USDT"}}
    sample = build_real_order_submission_gate(
        sample_data,
        sample_settings,
        {"symbol": "BTCUSDT", "side": "BUY", "quote_order_qty": 5},
        user="real_order_gate_quality_probe",
        role="owner",
    )
    checks = [
        "Final gate gerçek emir göndermeden karar üretir",
        "Gerçek emir endpointi backend tarafında final gate sonucunu dikkate alır",
        "Owner onayı ve GERCEK PARA metin onayı olmadan gerçek emir engellenir",
        "Readiness, dry-run, strateji/filtre ve runtime kilitleri aynı raporda toplanır",
        "Kullanıcıya sade blocker_texts döner",
    ]
    blockers = []
    if sample.get("real_order_created") is not False:
        blockers.append("submission gate gerçek emir oluşturuyor")
    for key in ["status", "simple_status", "real_order_allowed", "order", "blockers", "blocker_texts", "readiness", "dry_run", "runtime"]:
        if key not in sample:
            blockers.append(f"{key} eksik")
    if "owner_confirmed_missing" not in sample.get("blockers", []):
        blockers.append("owner onay blocker beklenirken üretilmedi")
    if "final_ack_missing" not in sample.get("blockers", []):
        blockers.append("GERCEK PARA metin onay blocker beklenirken üretilmedi")
    return {"status": "ok" if not blockers else "blocked", "checks": checks, "blockers": blockers, "sample_status": sample.get("status"), "sample": sample}
