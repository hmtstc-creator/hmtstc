# Paket 10 System Status and Runtime Store

## 1. Paket amaci

Paket 10, Dashboard uzerinde canli sistem durumunu gorunur yapar, frontend API hatalarini siniflandirir ve runtime `rule_store.json` dosyasinin sessiz bosalma riskini audit ile yakalar.

Bu paket yeni trade davranisi eklemez. Karabasan matematiği, Paper Lab kombinasyon matematiği, Binance, Futures, real-trade ve order executor davranisi degismedi.

## 2. Dashboard Sistem Durum Seridi

Dashboard wallet paneline `Sistem Durum Seridi` eklendi.

Gorunen alanlar:

- Backend API
- Bot Durumu
- Karabasan
- Paper Lab
- Rule Store
- Binance API

Bot butonu artik botun gercek durumunun tek kaynagi degildir. Gercek durum `/api/bot/status` ve Dashboard status seridinden okunur.

## 3. API hata siniflandirma

Ortak API client su hata tiplerini siniflandirir:

- `backend_offline`
- `cors_error`
- `timeout`
- `http_401`
- `http_403`
- `http_404`
- `http_500`
- `invalid_json`
- `unknown_network`

Kullanici mesaji kisa tutulur; endpoint ve hata tipi `HMTSTC_DATA.systemStatus` icinde gorunur hale gelir.

## 4. Bot start kontrolu

Bot start akisi su sekilde guclendirildi:

- Backend/API hazir degilse start denenmez.
- Start oncesi `/api/bot/status` okunur.
- Start request basarili olsa bile UI hemen aktif sayilmaz.
- Start sonrasi `/api/bot/status` tekrar okunur.
- Sadece backend status `bot_running=true` donerse bot aktif gorunur.

## 5. Paper Lab auto sync kontrolu

Auto Paper Lab akisi artik su durumlari ayirir:

- Backend erisilemiyor.
- Endpoint yok.
- Rule store bos.
- Filtre veya strateji eksik.
- Sync calisiyor.
- Model yok.
- Model sayisi hazir.

Bu degisiklik model kombinasyon matematiğini degistirmez.

## 6. Runtime rule_store korumasi

Backend `build_rule_store_status` ile aktif rule store sayilarini ve runtime backup adayini raporlar. Dashboard `Rule Store` satiri 0/0 durumunu kirmizi uyarı olarak gosterir.

Aktif rule store 0 rule iken backup icinde rule varsa:

- Otomatik restore yapilmaz.
- Dashboard uyarir.
- 40.15 audit blocker verir.
- Manuel restore icin `docs/RULE_STORE_RESTORE_RUNBOOK.md` kullanilir.

## 7. Degisen dosyalar

- `backend/services/rule_engine.py`
- `frontend/js/app/api.js`
- `frontend/js/app/bot.js`
- `frontend/js/app/rules.js`
- `frontend/js/pages/dashboard.js`
- `frontend/css/dashboard-funnel.css`
- `scripts/level1_40_15_system_status_runtime_store_audit.py`
- `docs/LEVEL1_40_15_SYSTEM_STATUS_RUNTIME_STORE_AUDIT.json`
- `docs/LEVEL1_40_15_SYSTEM_STATUS_RUNTIME_STORE_AUDIT.md`
- `docs/RULE_STORE_RESTORE_RUNBOOK.md`
- `docs/PACKAGE_10_SYSTEM_STATUS_AND_RUNTIME_STORE.md`
- `README.md`
- `todo.md`

## 8. Dokunulmayan kritik dosyalar

Su kritik alanlara dokunulmadi:

- `backend/binance_credentials_store.json`
- `backend/settings_store.json`
- `backend/shadow_store.json`
- `backend/services/*order*`
- `backend/services/*executor*`
- `backend/services/*binance*`
- `frontend/js/app/realTrade.js`
- `frontend/js/app/realApproval.js`
- `webhook_server.py`
- `deploy/*`

## 9. Test sonuclari

- `py -X pycache_prefix=.pycache_paket10 -m py_compile backend\main.py backend\routes\rule_routes.py backend\routes\dashboard_routes.py backend\services\rule_engine.py scripts\level1_40_07_frontend_api_inventory.py scripts\level1_40_08_api_contract_diff.py scripts\level1_40_09_missing_endpoint_report.py scripts\level1_40_10_mutating_endpoint_safety_audit.py scripts\level1_40_11_real_trade_manual_review_matrix.py scripts\level1_40_12_owner_approval_contract_audit.py scripts\level1_40_13_rule_selection_persistence_audit.py scripts\level1_40_14_rule_backend_stability_audit.py scripts\level1_40_15_system_status_runtime_store_audit.py`: pass
- `py scripts\level1_40_06_api_route_inventory.py`: pass, `route_count=891`
- `py scripts\level1_40_07_frontend_api_inventory.py`: pass, `call_count=89`, `unique_base_path_count=72`
- `py scripts\level1_40_08_api_contract_diff.py --strict`: pass, `matched_call_count=89`, `missing_path_count=0`, `method_mismatch_count=0`
- `py scripts\level1_40_09_missing_endpoint_report.py`: pass, `true_blocker_count=0`, `parser_gap_or_false_positive_count=0`
- `py scripts\level1_40_10_mutating_endpoint_safety_audit.py`: pass, `status=ok`, `mutating_call_count=50`, `unclassified_mutating_count=0`
- `py scripts\level1_40_11_real_trade_manual_review_matrix.py`: pass, `status=ok`, `critical_real_trade_count=13`, `unknown_real_trade_risk_type_count=0`
- `py scripts\level1_40_12_owner_approval_contract_audit.py`: pass, `status=ok`, `order_submission_contract_ok=true`
- `py scripts\level1_40_13_rule_selection_persistence_audit.py`: pass, `status=ok`, `draft_preserved_on_error=true`
- `py scripts\level1_40_14_rule_backend_stability_audit.py`: pass, `status=ok`, `activate_paper_lab_route_present=true`, `audit_failure_isolated=true`
- `py scripts\level1_40_15_system_status_runtime_store_audit.py`: pass, `status=ok`, `dashboard_status_panel_present=true`, `api_error_classifier_present=true`, `dashboard_rule_selection_reload_persistence_present=true`, `dashboard_no_fallback_all_on_explicit_backend_selection=true`, `dashboard_selected_filter_ids_render_present=true`, `dashboard_selected_strategy_ids_render_present=true`, `active_rule_store_total_rules=0`, `backup_max_rule_count=0`, `empty_active_backup_blocker=false`
- `py scripts\level1_40_15_audit_schema_tests_check.py`: kapsam disi / calistirilmadi. Paket 10 kalite kapisi `scripts\level1_40_15_system_status_runtime_store_audit.py` uzerindedir; `tests/unit/test_audit_schema.py` Paket 10 kapsaminda zorunlu dosya degildir.
- `node --check frontend\js\app\api.js`: calistirilamadi, Node PATH'te yok
- `node --check frontend\js\app\bot.js`: calistirilamadi, Node PATH'te yok
- `node --check frontend\js\app\rules.js`: calistirilamadi, Node PATH'te yok
- `node --check frontend\js\pages\dashboard.js`: calistirilamadi, Node PATH'te yok

Manuel kabul testi:

1. Dashboard acilir.
2. `Sistem Durum Seridi` icinde Backend API, Bot Durumu, Karabasan, Paper Lab, Rule Store ve Binance API satirlari gorulur.
3. Bot baslatildiginda UI ancak `/api/bot/status` start sonrasi `bot_running=true` donerse aktif gorunur.
4. Backend kapaliyken API hata tipi `backend_offline` veya tarayici kosuluna gore ilgili network sinifi olarak gorunur.
5. `/api/rules/auto-paper-lab` endpointi yoksa hata `http_404` ve endpoint bilgisiyle gorunur.
6. Rule Store 0/0 ise Dashboard kirmizi uyarı gosterir.
7. Aktif rule store 0 iken backup >0 olursa 40.15 audit blocker verir; otomatik restore yapilmaz.
8. Dashboard filtre/strateji secimi kaydedilir.
9. Site kapatilip tekrar acilir.
10. Backend `selected_filter_ids` ve `selected_strategy_ids` icindeki ayni secimler birebir geri gelir.
11. Daha once secilmeyen filtre/stratejiler tekrar secili gelirse Paket 10 fail sayilir.

## 10. Paket 11'e gecis karari

40.06-40.15 kalite zinciri temiz kaldigi ve `empty_active_backup_blocker=false` oldugu surece Paket 11'e gecis uygundur.
