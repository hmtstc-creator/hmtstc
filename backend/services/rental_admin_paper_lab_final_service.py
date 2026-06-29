"""Admin Paper Lab final contract for rental product.

Paper is owner-only laboratory; rented users stay on live Summary.
No order is placed here.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from services.paper_combination_performance_service import build_paper_combination_performance


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _safe_float(value: Any, fallback: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return fallback


def _safe_int(value: Any, fallback: int = 0) -> int:
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return fallback


def _row(area: str, current: str, expected: str, ok: bool, action: str) -> dict[str, Any]:
    return {
        "area": area,
        "current": current,
        "expected": expected,
        "ok": bool(ok),
        "action": action,
    }


def build_rental_admin_paper_lab_final(data: dict | None, settings: dict | None, role: str = "user", user: str = "default") -> dict[str, Any]:
    data = data if isinstance(data, dict) else {}
    settings = settings if isinstance(settings, dict) else {}
    is_owner = str(role or "user").lower() == "owner"
    performance = build_paper_combination_performance(data, settings, user=user)
    summary = performance.get("summary") or {}
    combinations = performance.get("combinations") or []
    strong = [item for item in combinations if item.get("decision") == "Güçlü"]
    watch = [item for item in combinations if item.get("decision") in {"İzle", "Daha çok izle"}]
    close = [item for item in combinations if item.get("decision") == "Kapat"]
    best = summary.get("best_combination") or (combinations[0] if combinations else {})
    best_trades = _safe_int(best.get("trade_count"), 0) if isinstance(best, dict) else 0
    best_pnl = _safe_float(best.get("net_pnl"), 0.0) if isinstance(best, dict) else 0.0
    best_win = _safe_float(best.get("win_rate"), 0.0) if isinstance(best, dict) else 0.0
    rows = [
        _row("Görünürlük", "Owner" if is_owner else "Gizli", "Paper Lab sadece admin/owner görmeli.", is_owner, "Son kullanıcı canlı Summary ekranında kalır."),
        _row("Kombinasyon", f"{len(combinations)} kayıt", "Strateji + filtre eşleşmeleri tek tabloda olmalı.", len(combinations) >= 0, "Test verisi geldikçe tablo dolar."),
        _row("Güçlü aday", f"{len(strong)} adet", "Canlıya önerilecek adaylar ayrı sayılmalı.", True, "Admin güçlü adayları canlıya açabilir."),
        _row("İzlenecek aday", f"{len(watch)} adet", "Yeterli veri yoksa izleme kararı verilmeli.", True, "Daha fazla paper örneği bekle."),
        _row("Kapat adayı", f"{len(close)} adet", "Zayıf kombinasyonlar kapatılabilmeli.", True, "Admin pasife alabilir."),
        _row("Canlı öneri", "Hazır" if best_trades >= 10 and best_pnl > 0 else "Bekle", "Minimum işlem ve pozitif net PnL aranmalı.", best_trades >= 10 and best_pnl > 0, "Win rate, net PnL ve drawdown birlikte kontrol edilir."),
    ]
    recommendations = []
    if isinstance(best, dict) and best:
        recommendations.append({
            "label": "En iyi kombinasyon",
            "strategy": best.get("strategy") or best.get("strategy_id") or "-",
            "filter": best.get("filter") or best.get("filter_id") or "-",
            "trade_count": best_trades,
            "net_pnl": round(best_pnl, 4),
            "win_rate": best_win,
            "decision": best.get("decision") or "İzle",
            "action": "Canlıya aç" if best_trades >= 10 and best_pnl > 0 else "Biraz daha izle",
        })
    status = "ready" if is_owner and not [row for row in rows if not row["ok"] and row["area"] != "Canlı öneri"] else "review"
    return {
        "status": status,
        "generated_at": _now_iso(),
        "owner_only": True,
        "user_visible": False,
        "simple_text": "Paper Lab son kullanıcıya değil, admin strateji/filtre kararına hizmet eder.",
        "rows": rows,
        "summary": {
            "combination_count": len(combinations),
            "strong_count": len(strong),
            "watch_count": len(watch),
            "close_count": len(close),
            "total_trades": _safe_int(summary.get("total_trades"), 0),
            "total_pnl": round(_safe_float(summary.get("total_pnl"), 0.0), 4),
        },
        "recommendations": recommendations,
        "top_combinations": combinations[:10],
        "next_action": "Admin güçlü adayları canlı kullanıma açar; son kullanıcı paper raporu görmez.",
    }


def build_rental_admin_paper_lab_final_quality_report() -> dict[str, Any]:
    sample_data = {
        "paper_lab": {"models": {"m1": {}}},
        "model_rankings": [
            {"strategy_id": "trend", "filter_id": "liquidity", "total_trades": 18, "win_rate": 0.67, "realized_pnl": 42.5, "score": 82, "eligible_for_real": True},
            {"strategy_id": "breakout", "filter_id": "news", "total_trades": 6, "win_rate": 0.48, "realized_pnl": -5.2, "score": 44},
        ],
    }
    report = build_rental_admin_paper_lab_final(sample_data, {}, role="owner", user="quality")
    blockers: list[str] = []
    if not report.get("owner_only"):
        blockers.append("not_owner_only")
    if report.get("user_visible") is not False:
        blockers.append("user_visibility_not_false")
    if len(report.get("rows") or []) < 6:
        blockers.append("rows_missing")
    if len(report.get("top_combinations") or []) < 1:
        blockers.append("combination_rows_missing")
    return {"status": "ok" if not blockers else "blocked", "blockers": blockers, "sample": report}
