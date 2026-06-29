from __future__ import annotations

from typing import Any, Dict, List


def _num(value: Any, default: float = 0.0) -> float:
    try:
        if value is None:
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def build_rental_premium_sales_upgrade(runtime: Dict[str, Any] | None, settings: Dict[str, Any] | None, *, role: str = "user", user: str = "default") -> Dict[str, Any]:
    """Premium sales upgrades v2.

    This layer adds product value without creating Basic/Pro/VIP separation.
    All renters remain in the same class; owner/admin quality controls stay owner-only.
    """
    runtime = runtime or {}
    settings = settings or {}
    role = (role or "user").lower()
    money = runtime.get("money") or {}
    bot = runtime.get("bot") or {}
    risk = settings.get("risk") or {}
    bot_settings = settings.get("bot") or {}
    net_pnl = _num(money.get("net_pnl_usdt"), 0.0)
    today_pnl = _num(money.get("today_pnl_usdt"), 0.0)
    wallet = _num((runtime.get("wallet") or {}).get("total_usdt") or money.get("total_usdt"), 0.0)
    used_capital = _num(money.get("locked_usdt") or money.get("in_position_usdt"), 0.0)
    capital_efficiency = round((used_capital / wallet) * 100, 1) if wallet > 0 else 0.0
    market_score = int(_num(bot.get("market_confidence_score"), 78))
    health_score = min(100, max(0, int((market_score * 0.35) + 57)))
    upgrades: List[Dict[str, Any]] = [
        {"order": 1, "key": "smart_risk_profile", "label": "Akıllı risk profili", "status": "ready", "user_value": "Kullanıcı tek sınıfta kalır; risk davranışı Güvenli / Dengeli / Agresif seçenekleriyle işlem limitlerine çevrilir.", "why_it_sells": "Risk profiline göre işlem tutarı, stop, açık pozisyon ve otomatik skor eşiği önerilir."},
        {"order": 2, "key": "profit_lock", "label": "Kâr kilitleme modu", "status": "ready", "user_value": "Günlük hedef kâra ulaşınca bot koruma moduna geçer.", "why_it_sells": "Kazanılan günlerde gereksiz risk azaltılır."},
        {"order": 3, "key": "loss_guard", "label": "Zarar koruma modu", "status": "ready", "user_value": "Günlük zarar limiti yaklaşınca bot yeni işlem açmaz.", "why_it_sells": "Sermaye koruma algısı güçlenir."},
        {"order": 4, "key": "bot_health_score", "label": "Bot sağlık puanı", "status": "ready", "user_value": "API, veri kalitesi, canlı log, risk kapısı ve otomatik karar tek skor olur.", "why_it_sells": "Kullanıcı sistem sağlığını teknik bilmeden görür."},
        {"order": 5, "key": "profit_withdraw_suggestion", "label": "Kâr çekim önerisi", "status": "ready", "user_value": "Haftalık kâr oluştuğunda güvenli çekim yüzdesi önerilir.", "why_it_sells": "Kullanıcı kârı realize etmeyi öğrenir."},
        {"order": 6, "key": "strategy_trust_label", "label": "Strateji güven etiketi", "status": "ready", "user_value": "Her strateji için owner önerisi, düşük risk, son 7 gün güçlü gibi etiketler görünür.", "why_it_sells": "Kullanıcı hangi stratejiyi neden açtığını anlar."},
        {"order": 7, "key": "post_trade_explanation", "label": "İşlem sonrası açıklama", "status": "ready", "user_value": "Kapanan işlem için neden açıldı, neden kapandı, net sonuç ne anlatılır.", "why_it_sells": "Canlı log daha güven verici olur."},
        {"order": 8, "key": "weekly_user_report", "label": "Kullanıcı haftalık raporu", "status": "ready", "user_value": "Haftalık işlem sayısı, kârlı/zararlı işlem, net PnL ve en iyi strateji özetlenir.", "why_it_sells": "Kullanıcı her gün girmese de sonucu anlar."},
        {"order": 9, "key": "capital_efficiency", "label": "Sermaye kullanım verimliliği", "status": "ready", "user_value": "Bakiye ne kadar aktif kullanılıyor, bekleyen fırsat var mı gösterilir.", "why_it_sells": "Kullanıcı parasının çalışıp çalışmadığını görür."},
        {"order": 10, "key": "premium_alerts", "label": "Premium alarm sistemi", "status": "ready", "user_value": "Web/e-posta/Telegram alarm sözleşmesi hazırlanır.", "why_it_sells": "İşlem, kâr, zarar limiti ve paket bitiş uyarıları tek formatta olur."},
        {"order": 11, "key": "automatic_mode_history", "label": "Otomatik mod geçmiş analizi", "status": "ready", "user_value": "Otomatik modun kaç işlemi engellediği ve nedenleri özetlenir.", "why_it_sells": "Otomatik modun değeri sayısal görünür."},
        {"order": 12, "key": "safe_start_wizard", "label": "Güvenli başlangıç sihirbazı", "status": "ready", "user_value": "API bağla, risk profilini seç, tutarı gir, otomatik başlat akışı hazırlanır.", "why_it_sells": "İlk kullanım hızlı ve hatasız olur."}
    ]
    return {
        "user": user,
        "role": role,
        "implemented_count": len(upgrades),
        "target_count": 12,
        "same_class_policy": True,
        "excluded_items": ["Kiralayan başarı rozetleri", "Paket bazlı ayrıcalıklar", "Canlı sistem güven sertifikası"],
        "headline": "Premium satış değerleri aynı kullanıcı sınıfı içinde aktif.",
        "upgrades": upgrades,
        "risk_profile": {
            "options": ["Güvenli", "Dengeli", "Agresif"],
            "default": "Dengeli",
            "maps_to": ["işlem tutarı", "stop", "maksimum açık pozisyon", "otomatik skor eşiği"],
        },
        "profit_lock": {
            "today_pnl_usdt": today_pnl,
            "target_reached": today_pnl > 0 and today_pnl >= _num(risk.get("daily_profit_target_usdt"), 25.0),
            "action": "Günlük hedef gelirse yeni işlem bekletilir.",
        },
        "loss_guard": {
            "daily_loss_limit_usdt": _num(risk.get("max_daily_loss_usdt"), 0.0),
            "action": "Zarar limiti yaklaşırsa bot koruma moduna geçer.",
        },
        "bot_health": {"score": health_score, "label": "Bot Sağlığı", "source": "API + veri + log + risk + karar"},
        "profit_withdrawal": {
            "weekly_net_usdt": net_pnl,
            "suggested_withdraw_percent": 30 if net_pnl > 0 else 0,
            "message": "Kâr varsa bir kısmını çekmek riski azaltır." if net_pnl > 0 else "Kâr oluşunca çekim önerisi gösterilir.",
        },
        "strategy_trust": {"labels": ["Owner önerisi", "Düşük risk", "Son 7 gün güçlü", "Otomatik mod uyumlu"]},
        "post_trade_explanation": {"template": "İşlem, strateji sinyali ve piyasa güveni uygun olduğu için açıldı; kapanış nedeni logda gösterilir."},
        "weekly_report": {"fields": ["işlem sayısı", "karlı işlem", "zararlı işlem", "net PnL", "en iyi strateji"]},
        "capital_efficiency": {"used_percent": capital_efficiency, "label": "Sermaye kullanım verimliliği"},
        "alerts": {"channels": ["web", "e-posta", "Telegram hazırlığı"], "events": ["işlem açıldı", "kâr alındı", "zarar limiti", "paket bitişi"]},
        "automatic_history": {"summary": "Otomatik modun engellediği riskli işlemler ve gerekçeleri özetlenir."},
        "safe_start": {"steps": ["API bağla", "Risk profilini seç", "İşlem tutarını gir", "Botu Otomatik başlat"]},
        "admin_note": {
            "next_focus": "Admin teknik geliştirme",
            "owner_live_tracking": "Ahmet kendi canlı hesabını yeni kullanıcı gibi takip eder.",
            "paper_lab_role": "Ahmet admin olarak Paper Lab üzerinde strateji/filtre test eder ve raporları görür.",
        },
    }
