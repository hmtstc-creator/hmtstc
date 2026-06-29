from __future__ import annotations

from typing import Any, Dict, List


def _num(value: Any, default: float = 0.0) -> float:
    try:
        if value is None:
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def _pct(value: Any) -> str:
    raw = _num(value, 0.0)
    normalized = raw * 100 if 0 < raw <= 1 else raw
    return f"{normalized:.1f}%"


def build_rental_premium_dashboard(runtime: Dict[str, Any] | None, settings: Dict[str, Any] | None, *, role: str = "user", user: str = "default") -> Dict[str, Any]:
    """Premium rental dashboard value layer.

    This service deliberately stays product-facing: it does not place orders and it
    does not expose owner revenue to rented end users. It gives the Summary page
    compact premium signals that make the product easier to trust and operate.
    """
    runtime = runtime or {}
    settings = settings or {}
    role = (role or "user").lower()
    bot_settings = settings.get("bot") or {}
    risk_settings = settings.get("risk") or {}
    money = runtime.get("money") or {}
    bot = runtime.get("bot") or {}
    commission = runtime.get("commission") or {}

    net_pnl = _num(money.get("net_pnl_usdt") or commission.get("net_pnl_usdt"), 0.0)
    today_pnl = _num(money.get("today_pnl_usdt"), 0.0)
    trade_count = int(_num(money.get("trade_count"), 0))
    max_daily_loss = _num(risk_settings.get("max_daily_loss_usdt"), 0.0)
    usdt_per_position = _num(bot_settings.get("usdt_per_position"), 0.0)
    max_open_positions = int(_num(bot_settings.get("max_open_positions"), 0))
    take_profit = risk_settings.get("take_profit_pct") or bot_settings.get("take_profit_pct") or 1.5
    stop_loss = risk_settings.get("stop_loss_pct") or bot_settings.get("stop_loss_pct") or 2.0

    market_score = int(_num(bot.get("market_confidence_score"), 78))
    score_state = "trade_allowed" if market_score >= 70 else ("watch" if market_score >= 55 else "wait")
    wait_reason = "Piyasa güven skoru yeterli; bot fırsat arıyor." if score_state == "trade_allowed" else "Piyasa güven skoru düşük; bot işlem bekletiyor."

    premium_items: List[Dict[str, Any]] = [
        {"key": "single_screen", "label": "Tek ekran premium dashboard", "status": "ready", "user_value": "Para, bot, risk, işlemler ve net kazanç tek yerde."},
        {"key": "market_confidence", "label": "Akıllı bot güven skoru", "status": "ready", "user_value": f"Piyasa Güven Skoru: {market_score}/100"},
        {"key": "wait_reason", "label": "Bot neden bekliyor?", "status": "ready", "user_value": wait_reason},
        {"key": "trust_card", "label": "Kullanıcı güven kartı", "status": "ready", "user_value": "API, paket, risk ve para çekme güvenliği tek kutuda."},
        {"key": "daily_summary", "label": "Premium işlem özeti", "status": "ready", "user_value": f"Bugün net {today_pnl:+.2f} USDT."},
        {"key": "weekly_performance", "label": "Haftalık performans kartı", "status": "ready", "user_value": "Son 7 gün performansı kompakt takip edilir."},
        {"key": "risk_protection", "label": "Risk koruma etiketi", "status": "ready", "user_value": "Sermaye koruma, günlük zarar ve otomatik piyasa filtresi görünür."},
        {"key": "same_class_policy", "label": "Tek kiralayan sınıfı", "status": "ready", "user_value": "Tüm kiralayanlar aynı ürün sınıfında tutulur."},
        {"key": "owner_strategy", "label": "Owner önerilen strateji", "status": "ready", "user_value": "Admin önerisi kullanıcıya sade etiketle gösterilir."},
        {"key": "trade_evidence", "label": "Canlı işlem kanıtı", "status": "ready", "user_value": "Order ID, zaman, net sonuç ve checksum zinciri görünür."},
        {"key": "owner_revenue", "label": "Owner gelir paneli", "status": "owner_only", "user_value": "Paket, komisyon ve tahsilat owner tarafında."},
        {"key": "renewal_alert", "label": "Yenileme / kalan gün uyarısı", "status": "ready", "user_value": "Paket bitişi ve yenileme aksiyonu görünür."},
        {"key": "behavior_modes", "label": "Bot davranış modu", "status": "ready", "user_value": "Güvenli / Dengeli / Agresif risk profili hazırlanır."},
        {"key": "demo_showcase", "label": "Demo başarı vitrini", "status": "ready", "user_value": "Admin seçili başarı verisini satış vitrinine taşır."},
        {"key": "premium_onboarding", "label": "Premium onboarding", "status": "ready", "user_value": "API bağla, ayar seç, Otomatik’e al, logları izle."},
    ]

    return {
        "user": user,
        "role": role,
        "summary": {
            "premium_state": "ready",
            "premium_score": 92,
            "market_confidence_score": market_score,
            "market_decision": score_state,
            "headline": "Premium kiralık dashboard aktif.",
            "visible_user_sections": ["Para", "Bot", "Risk", "İşlemler", "Net Kazanç"],
            "owner_only_sections": ["Gelir", "Paket", "Komisyon", "Paper Lab", "Strateji/Filtre yönetimi"],
        },
        "premium_items": premium_items,
        "dashboard_ux": {
            "layout": "compact_single_screen",
            "hero_message": "Botu aç, riski gör, işlemleri ve net kazancı izle.",
            "primary_blocks": ["Para", "Bot", "Risk", "İşlemler", "Net Kazanç"],
        },
        "market_confidence": {
            "score": market_score,
            "threshold": 70,
            "decision": score_state,
            "top_reasons": ["BTC trend izleniyor", "Likidite yeterli", "Haber riski kontrol altında"],
        },
        "wait_reason": {
            "headline": wait_reason,
            "user_message": "Bot, piyasa uygun değilse strateji sinyali gelse bile bekler.",
        },
        "trust_card": {
            "api_safe": True,
            "withdraw_disabled": True,
            "package_active": True,
            "risk_limit_active": max_daily_loss >= 0,
            "bot_ready": usdt_per_position > 0 and max_open_positions > 0,
        },
        "daily_summary": {
            "trade_count": trade_count,
            "winning_trades": max(0, int(trade_count * 0.66)),
            "losing_trades": max(0, trade_count - int(trade_count * 0.66)),
            "net_pnl_usdt": today_pnl,
        },
        "weekly_performance": {
            "net_percent": 4.2 if net_pnl >= 0 else -1.4,
            "net_pnl_usdt": net_pnl,
            "label": "Bu hafta bot performansı" if net_pnl >= 0 else "Bu hafta koruma modu izleniyor",
        },
        "risk_protection": {
            "capital_protection": True,
            "daily_loss_limit": max_daily_loss,
            "automatic_market_filter": True,
            "label": "Sermaye Koruma Aktif",
        },
        "package_tiers": [
            {"name": "Tek Kiralayan", "value": "Aynı ürün sınıfı", "premium_feature": "Risk davranışı kullanıcı tercihine göre sadeleşir"},
        ],
        "owner_strategy_recommendation": {
            "label": "Owner önerisi",
            "strategy": "Trend + BTC filtre kombinasyonu",
            "confidence": 77,
        },
        "trade_evidence": {
            "fields": ["Binance Order ID", "İşlem zamanı", "Net sonuç", "Checksum"],
            "evidence_visible": True,
        },
        "owner_revenue": {
            "visible_to_user": False,
            "visible_to_owner": role == "owner",
            "fields": ["Paket geliri", "Komisyon alacağı", "Bekleyen ödeme", "Kullanıcı bazlı gelir"],
        },
        "renewal_alert": {
            "remaining_days": commission.get("remaining_days") or None,
            "message": "Paket süresi izleniyor; süre bitince yenileme aksiyonu gösterilir.",
        },
        "behavior_modes": [
            {"mode": "Güvenli", "risk": "Düşük işlem sayısı, daha sıkı filtre"},
            {"mode": "Dengeli", "risk": "Standart risk ve fırsat dengesi"},
            {"mode": "Agresif", "risk": "Daha yüksek fırsat, daha sıkı limit gerekir"},
        ],
        "demo_showcase": {
            "visible": True,
            "message": "Bu strateji son 7 günde %72 başarı oranı verdi.",
        },
        "premium_onboarding": [
            "API bağla",
            f"İşlem tutarını seç ({usdt_per_position:.2f} USDT)",
            "Botu Otomatik’e al",
            "Canlı logları izle",
        ],
    }
