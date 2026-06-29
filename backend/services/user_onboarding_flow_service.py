from __future__ import annotations

from typing import Any

from core.storage import now_iso
from services.binance_api_connection_service import get_connection_summary
from services.binance_wallet_summary_service import build_wallet_summary
from services.strategy_filter_toggle_service import get_strategy_filter_toggles
from services.paper_combination_performance_service import build_paper_combination_performance
from services.live_trade_readiness_check_service import build_live_trade_readiness_check


def _truthy(value: Any) -> bool:
    return bool(value)


def _money(value: Any) -> float:
    try:
        return round(float(value or 0), 4)
    except Exception:
        return 0.0


def _step(key: str, title: str, done: bool, action: str, page: str, note: str, uses_real_money: bool = False) -> dict:
    return {
        "key": key,
        "title": title,
        "done": bool(done),
        "status": "done" if done else "todo",
        "simple_status": "Tamam" if done else "Eksik",
        "action": action,
        "page": page,
        "note": note,
        "uses_real_money": bool(uses_real_money),
    }


def _first_open_step(steps: list[dict]) -> dict | None:
    for item in steps:
        if not item.get("done"):
            return item
    return None


def build_user_onboarding_flow(data: dict | None, settings: dict | None, user: str = "default") -> dict:
    """Build a plain onboarding checklist for a non-technical user.

    This is read-only. It does not save keys, start the bot, place orders, or
    change strategy/filter settings. It only tells the user the next simple step.
    """
    data = data if isinstance(data, dict) else {}
    settings = settings if isinstance(settings, dict) else {}

    connection_payload = get_connection_summary(user)
    connection = connection_payload.get("connection") or {}
    has_binance = bool(connection.get("has_api_key") and connection.get("has_api_secret"))
    environment = connection.get("environment") or "testnet"

    wallet_payload = build_wallet_summary(user)
    wallet = wallet_payload.get("wallet") or {}
    wallet_known = str(wallet.get("status") or wallet_payload.get("status") or "").lower() not in {"missing", "blocked"}
    wallet_total = _money(wallet.get("wallet_total_usdt") or wallet.get("available_usdt"))

    toggles = get_strategy_filter_toggles(user)
    active_strategy_count = int(toggles.get("active_strategy_count") or 0)
    active_filter_count = int(toggles.get("active_filter_count") or 0)

    paper_payload = build_paper_combination_performance(data, settings, user=user)
    combinations = paper_payload.get("combinations") or []
    paper_summary = paper_payload.get("summary") or {}
    best = paper_summary.get("best_combination") if isinstance(paper_summary.get("best_combination"), dict) else None
    paper_has_result = bool(combinations)
    paper_good = bool(best and str(best.get("decision") or "") in {"Güçlü", "İzle", "Daha çok izle"})

    readiness = build_live_trade_readiness_check(data, settings, user=user)
    micro_ready = bool(readiness.get("ready_for_real_order"))

    steps = [
        _step(
            "binance_connection",
            "Binance bağla",
            has_binance,
            "Ayarlar ekranına git ve Binance API bilgilerini kaydet.",
            "settings",
            "Bu adım sadece bağlantı içindir. Tek başına emir göndermez.",
        ),
        _step(
            "wallet_check",
            "Paramı gör",
            has_binance and wallet_known,
            "Param ekranında USDT bakiyesinin nereden geldiğini kontrol et.",
            "summary",
            f"Görünen takip bakiyesi: {wallet_total:.2f} USDT.",
        ),
        _step(
            "strategy_filter_selection",
            "Strateji ve filtre seç",
            active_strategy_count > 0 and active_filter_count > 0,
            "Bot Kumandası ekranında en az 1 strateji ve 1 filtre açık bırak.",
            "botControl",
            "Strateji botun fikridir; filtre kötü işlemi engeller.",
        ),
        _step(
            "paper_watch",
            "Gerçek para olmadan izle",
            paper_has_result,
            "Paper Sonuçları ekranında hangi kombinasyon para kazandırıyor bak.",
            "paperLabModels",
            "Paper gerçek para kullanmaz; sistemi önce burada izle.",
        ),
        _step(
            "paper_decision",
            "İyi çalışan fikri seç",
            paper_good,
            "Güçlü veya izlenebilir görünen kombinasyonu canlı aday olarak değerlendir.",
            "paperLabModels",
            "Zayıf kombinasyon gerçek paraya taşınmamalı.",
        ),
        _step(
            "micro_live_ready",
            "Mikro canlıya hazırlan",
            micro_ready,
            "Canlı İşlem ekranında mikro kontrol yap. İlk deneme küçük tutarla olmalı.",
            "tradingControl",
            "Bu adım gerçek para riski taşıyabilir; tüm kilitler kapalıysa emir çıkmaz.",
            uses_real_money=True,
        ),
    ]
    done_count = sum(1 for item in steps if item.get("done"))
    next_step = _first_open_step(steps)
    if next_step:
        simple_status = next_step.get("action") or "Sonraki adımı tamamla."
        status = "in_progress"
    else:
        simple_status = "Başlangıç tamam. Artık sistemi güvenle izleyebilirsin."
        status = "ready"

    return {
        "status": status,
        "user": user,
        "simple_status": simple_status,
        "done_count": done_count,
        "total_steps": len(steps),
        "progress_percent": round(done_count / max(len(steps), 1) * 100, 1),
        "next_step": next_step,
        "steps": steps,
        "summary": {
            "binance_connected": has_binance,
            "environment": environment,
            "wallet_total_usdt": wallet_total,
            "active_strategy_count": active_strategy_count,
            "active_filter_count": active_filter_count,
            "paper_combination_count": len(combinations),
            "best_combination": best or {},
            "micro_live_ready": micro_ready,
        },
        "plain_explanation": "Bu ekran yeni kullanıcının sırayla ne yapacağını gösterir. Teknik detay göstermez ve gerçek emir göndermez.",
        "real_order_created": False,
        "generated_at": now_iso(),
    }


def build_user_onboarding_quality_report(data: dict | None, settings: dict | None, user: str = "default") -> dict:
    payload = build_user_onboarding_flow(data, settings, user=user)
    steps = payload.get("steps") or []
    checks = {
        "has_steps": len(steps) >= 6,
        "has_next_step": "next_step" in payload,
        "has_plain_status": bool(payload.get("simple_status")),
        "has_binance_step": any(item.get("key") == "binance_connection" for item in steps),
        "has_strategy_filter_step": any(item.get("key") == "strategy_filter_selection" for item in steps),
        "has_paper_step": any(item.get("key") == "paper_watch" for item in steps),
        "has_micro_live_step": any(item.get("key") == "micro_live_ready" for item in steps),
        "does_not_place_order": payload.get("real_order_created") is False,
        "all_steps_have_page": all(bool(item.get("page")) for item in steps),
    }
    blockers = [name for name, ok in checks.items() if not ok]
    return {
        "status": "ok" if not blockers else "blocked",
        "checks": checks,
        "blockers": blockers,
        "step_count": len(steps),
        "generated_at": now_iso(),
    }
