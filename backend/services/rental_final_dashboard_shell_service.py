"""Rental Final Dashboard shell contract.

This service keeps the rented-user product shape explicit:
- normal users operate from one Summary/Dashboard page only
- settings are inline panels inside Summary
- Paper Lab and technical/admin tools stay owner-only
- legacy backend names may remain for compatibility, but the UI contract must not ask users to choose paper/live/shadow
"""
from __future__ import annotations

from typing import Any


def _role_label(role: str | None) -> str:
    return "Owner/Admin" if str(role or "").lower() == "owner" else "Kiralayan kullanıcı"


def build_rental_final_dashboard_shell(role: str | None = "user") -> dict[str, Any]:
    role_value = str(role or "user").lower()
    is_owner = role_value == "owner"

    user_visible_pages = ["summary"]
    user_hidden_pages = [
        "settings",
        "paperLabModels",
        "ruleEditor",
        "users",
        "reports",
        "logs",
        "dashboard",
        "systemStatus",
        "tradingControl",
        "strategyGovernance",
    ]
    inline_user_panels = [
        "api_connection",
        "wallet_and_pnl",
        "bot_control_closed_open_automatic",
        "transaction_settings",
        "strategy_filter_toggles",
        "automatic_decision_scores",
        "live_trade_logs",
        "package_payment_risk_status",
    ]
    owner_only_panels = [
        "paper_lab",
        "strategy_filter_editor",
        "user_package_commission_management",
        "open_gap_report",
        "technical_reports",
    ]

    rows = [
        {
            "area": "Kullanıcı ekranı",
            "current": "Summary",
            "expected": "Kiralayan kişi tek sayfadan kullanmalı.",
            "ok": True,
            "action": "Menü son kullanıcıda gizli tutulur.",
        },
        {
            "area": "Ayar yapısı",
            "current": "Summary içi panel",
            "expected": "Lot, tutar, risk ve coin listesi ayrı sayfaya taşınmamalı.",
            "ok": True,
            "action": "Inline panel / drawer yaklaşımı korunur.",
        },
        {
            "area": "Bot kontrolü",
            "current": "Kapalı / Açık / Otomatik",
            "expected": "Kullanıcı bot kararını üç net seçenekle yönetmeli.",
            "ok": True,
            "action": "Mod seçimi değil ürün kontrolü olarak göster.",
        },
        {
            "area": "Paper Lab",
            "current": "Admin alanı",
            "expected": "Son kullanıcı paper analiziyle boğulmamalı.",
            "ok": True,
            "action": "Owner strateji/filtre kararlarını Paper Lab’da izler.",
        },
        {
            "area": "Shadow",
            "current": "Kullanıcı akışında yok",
            "expected": "Shadow seçeneği sorulmamalı.",
            "ok": True,
            "action": "Legacy isimler sadece teknik uyumlulukta kalır.",
        },
        {
            "area": "Canlı log",
            "current": "Summary içinde",
            "expected": "Alış, satış, fee, sistem payı ve net sonuç tek yerde görünmeli.",
            "ok": True,
            "action": "Log kartı ana ürün alanı olarak kalır.",
        },
    ]

    return {
        "status": "ready",
        "role": role_value,
        "role_label": _role_label(role_value),
        "user_visible_pages": user_visible_pages,
        "user_hidden_pages": user_hidden_pages,
        "inline_user_panels": inline_user_panels,
        "owner_only_panels": owner_only_panels if is_owner else [],
        "owner_available": is_owner,
        "navigation_mode": "single_page_user_shell",
        "menu_policy": "user_no_menu_owner_admin_shortcuts",
        "summary_is_live_dashboard": True,
        "settings_are_inline": True,
        "paper_lab_admin_only": True,
        "shadow_option_removed": True,
        "mode_selection_removed": True,
        "rows": rows,
        "simple_text": "Kiralayan kullanıcı için ürün tek Summary ekranıdır; admin aynı ekrandan canlıyı izler, Paper Lab ve yönetim araçları owner alanında kalır.",
        "next_action": "Canlı log ve otomatik karar kalitesini gerçek veriyle besle.",
        "blockers": [],
    }


def build_rental_final_dashboard_shell_quality_report() -> dict[str, Any]:
    user_shell = build_rental_final_dashboard_shell("user")
    owner_shell = build_rental_final_dashboard_shell("owner")
    blockers: list[str] = []
    if user_shell.get("user_visible_pages") != ["summary"]:
        blockers.append("user_not_single_summary")
    if user_shell.get("owner_only_panels"):
        blockers.append("owner_panels_visible_to_user")
    if owner_shell.get("paper_lab_admin_only") is not True:
        blockers.append("paper_lab_not_admin_only")
    if user_shell.get("shadow_option_removed") is not True:
        blockers.append("shadow_option_not_removed")
    if user_shell.get("settings_are_inline") is not True:
        blockers.append("settings_not_inline")
    return {
        "status": "ok" if not blockers else "blocked",
        "blockers": blockers,
        "user_shell": user_shell,
        "owner_shell": owner_shell,
    }
