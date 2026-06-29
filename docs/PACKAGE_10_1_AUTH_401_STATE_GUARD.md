# Paket 10.1 Auth 401 State Guard

## 1. Paket amaci

Paket 10.1, backend calisirken 401/auth probleminin `backend_offline` gibi gorunmesini engeller. Logout akisini ReferenceError uretmeyecek sekilde guclendirir ve 401 sonrasinda son basarili filtre/strateji listesini korur.

Bu paket yeni trade davranisi eklemez. Karabasan matematiği, Paper Lab kombinasyon matematiği, Binance, Futures, real-trade ve order executor davranisi degismedi.

## 2. Degisen davranis

- `frontend/js/app/auth.js` icindeki `HMTSTSTC_APP` typo kaldirildi.
- Logout akisi `window.HMTSTC_APP` yoksa crash uretmeyecek hale getirildi.
- `/api/auth/logout` 401 donerse logout temizligi yine tamamlanir.
- `getAuthHeaders` artik `window.HMTSTC_APP` guvenli referansi ile token okur.
- 401 durumunda `backend_api=online`, `auth_status=auth_expired` yazilir.
- 401 durumunda `HMTSTC_DATA.rules` bosaltilmaz; son basarili liste korunur.
- Dashboard sistem durum seridine `Oturum` satiri eklendi.
- Rules refresh ve Auto Paper Lab hata mesajlari 401 icin oturum uyarisi verir.

## 3. Degisen dosyalar

- `frontend/js/app/auth.js`
- `frontend/js/app/api.js`
- `frontend/js/app/rules.js`
- `frontend/js/pages/dashboard.js`
- `scripts/level1_40_16_auth_401_state_guard_audit.py`
- `docs/LEVEL1_40_16_AUTH_401_STATE_GUARD_AUDIT.json`
- `docs/LEVEL1_40_16_AUTH_401_STATE_GUARD_AUDIT.md`
- `docs/PACKAGE_10_1_AUTH_401_STATE_GUARD.md`
- `README.md`
- `todo.md`

## 4. Dokunulmayan kritik dosyalar

- `backend/binance_credentials_store.json`
- `backend/settings_store.json`
- `backend/shadow_store.json`
- `backend/rule_store.json`
- `backend/services/*order*`
- `backend/services/*executor*`
- `backend/services/*binance*`
- `frontend/js/app/realTrade.js`
- `frontend/js/app/realApproval.js`
- `webhook_server.py`
- `deploy/*`

## 5. Test sonuclari

- `py -X pycache_prefix=.pycache_paket10_1 -m py_compile scripts\level1_40_16_auth_401_state_guard_audit.py`: pass
- `py scripts\level1_40_13_rule_selection_persistence_audit.py`: pass, `status=ok`, `draft_preserved_on_error=true`
- `py scripts\level1_40_14_rule_backend_stability_audit.py`: pass, `status=ok`, `activate_paper_lab_route_present=true`, `audit_failure_isolated=true`
- `py scripts\level1_40_15_system_status_runtime_store_audit.py`: pass, `status=ok`, `dashboard_status_panel_present=true`, `api_error_classifier_present=true`, `dashboard_rule_selection_reload_persistence_present=true`
- `py scripts\level1_40_16_auth_401_state_guard_audit.py`: pass, `status=ok`, `auth_typo_hmtststc_absent=true`, `auth_logout_safe_app_guard_present=true`, `api_get_auth_headers_safe_app_guard_present=true`, `api_401_not_backend_offline=true`, `api_401_preserve_rules_present=true`, `rules_401_preserve_last_good_present=true`, `dashboard_auth_expired_status_present=true`
- `py scripts\level1_40_07_frontend_api_inventory.py`: pass, `call_count=89`, `unique_base_path_count=72`
- `py scripts\level1_40_08_api_contract_diff.py --strict`: pass, `matched_call_count=89`, `missing_path_count=0`, `method_mismatch_count=0`
- `py scripts\level1_40_09_missing_endpoint_report.py`: pass, `true_blocker_count=0`, `parser_gap_or_false_positive_count=0`
- `node --check frontend\js\app\auth.js`: calistirilamadi, Node PATH'te yok. Bloklayici degil; JS statik audit ve manuel kabul testi ile kontrol edildi.
- `node --check frontend\js\app\api.js`: calistirilamadi, Node PATH'te yok. Bloklayici degil; JS statik audit ve manuel kabul testi ile kontrol edildi.
- `node --check frontend\js\app\rules.js`: calistirilamadi, Node PATH'te yok. Bloklayici degil; JS statik audit ve manuel kabul testi ile kontrol edildi.
- `node --check frontend\js\pages\dashboard.js`: calistirilamadi, Node PATH'te yok. Bloklayici degil; JS statik audit ve manuel kabul testi ile kontrol edildi.

## 6. Manuel kabul testi

1. Dashboard acikken cikis yapilir.
2. Console'da `HMTSTC_APP` veya `HMTSTSTC_APP` ReferenceError gorulmez.
3. `/api/auth/logout` 401 donse bile UI crash olmaz.
4. Token gecersiz oldugunda Backend API offline gorunmez.
5. Oturum satiri `Suresi Doldu` durumunu gosterir.
6. `/api/rules` 401 dondugunde son basarili filtre/strateji listesi korunur.
7. Paper Lab sonrasi refresh 401/timeout verirse ana basari sonucu silinmez.

## 7. Paket 11'e gecis karari

40.13, 40.14, 40.15 ve 40.16 auditleri `ok` kaldigi surece Paket 11'e gecis uygundur.
