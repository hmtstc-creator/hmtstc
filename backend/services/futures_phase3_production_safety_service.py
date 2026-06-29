from __future__ import annotations

from typing import Any, Dict, List

from services.binance_futures_models import now_iso
from services.futures_phase2_evidence_gate_service import build_phase2_final_gate
from services.futures_phase3_mobile_experience_service import build_phase3_mobile_futures_experience
from services.futures_phase3_rental_finance_service import build_phase3_rental_finance_link
from services.futures_phase3_user_experience_service import build_phase3_user_futures_experience


def build_phase3_production_safety_final(
    runtime: Dict[str, Any],
    permission: Dict[str, Any],
    connection: Dict[str, Any],
    context: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    context = context or {}
    checks: List[Dict[str, Any]] = []

    def add(name: str, passed: bool, detail: str) -> None:
        checks.append({"name": name, "passed": bool(passed), "detail": detail})

    phase2_gate = build_phase2_final_gate(runtime, permission, connection, context)
    user_exp = build_phase3_user_futures_experience(runtime, permission, connection, context)
    finance = build_phase3_rental_finance_link(runtime, permission, context, owner_view=True)
    mobile = build_phase3_mobile_futures_experience(permission, {"critical_action": "open_live"})

    add("secret_not_returned_to_frontend", not context.get("secret_leak_detected"), "API secret frontend/log çıktısında bulunmamalı.")
    add("rate_limit_guard_enabled", bool(context.get("rate_limit_guard_enabled", True)), "Binance rate limit guard aktif olmalı.")
    add("retry_backoff_enabled", bool(context.get("retry_backoff_enabled", True)), "Hata halinde retry/backoff kontrollü olmalı.")
    add("vps_state_recovery_ready", bool(context.get("state_recovery_ready", True)), "VPS restart sonrası bot state ve açık pozisyonlar yüklenmeli.")
    add("healthcheck_ready", bool(context.get("healthcheck_ready", True)), "Admin production status healthcheck çalışmalı.")
    add("critical_error_blocks_orders", bool(context.get("critical_error_blocks_orders", True)), "Critical error yeni emirleri durdurmalı.")
    add("phase2_gate_passed", bool(phase2_gate.get("phase2_final_gate_passed", phase2_gate.get("phase2_ready", False))), "Funding/position/auto-close/alarm/evidence yeşil olmalı.")
    add("user_experience_ready", bool(user_exp.get("rental_ready_user_experience")), "Nihai kullanıcı sade ve güvenli Futures deneyimi görmeli.")
    add("commercial_finance_ready", bool(finance.get("commercial_ready")), "Kiralama, tahsilat ve komisyon bağlantısı hazır olmalı.")
    add("mobile_safety_ready", bool(mobile.get("wrong_tap_prevention")), "Mobil yanlış dokunma önlemleri aktif olmalı.")

    passed = all(c["passed"] for c in checks)
    return {
        "service": "futures_phase3_production_safety_final",
        "phase": "Faz3-5",
        "checked_at": now_iso(),
        "phase3_final_gate_passed": passed,
        "rental_ready": passed,
        "real_mainnet_order_policy": "owner_controlled_live_gate_only",
        "critical_blocks": [c for c in checks if not c["passed"]],
        "checks": checks,
        "phase2_gate": phase2_gate,
        "user_experience": user_exp,
        "finance": finance,
        "mobile": mobile,
    }
