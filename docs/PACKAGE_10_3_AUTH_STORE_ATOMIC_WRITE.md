# Paket 10.3 Auth Store Atomic Write

## 1. Paket amaci

Paket 10.3, eszamanli login/logout/auth yazimlarinda `auth_store.json.tmp` cakismasini engeller ve frontend login double-submit davranisini kapatir.

Bu paket Binance, Futures, real-trade, order executor, Karabasan matematiği, Paper Lab model matematiği ve canlı emir davranisini degistirmez.

## 2. Kok neden

Canli loglarda `auth_store.json.tmp -> auth_store.json` tasimasinda `FileNotFoundError` goruldu. Kisa surede birden fazla login istegi ayni ortak tmp dosyasini kullaninca bir yazim digerinin tmp dosyasini replace etmis olabiliyor.

## 3. Degisen davranis

- Auth store yazimi artik tek ortak `auth_store.json.tmp` kullanmaz.
- Her yazim benzersiz tmp dosya olusturur.
- Yazim ve `os.replace` RLock altinda calisir.
- Auth read-modify-write akislari lock altina alindi.
- Auth store yazim hatasi login endpointinde kontrollu `auth_store_error` cevabina doner.
- Frontend login `loginInProgress` ile ikinci istegi engeller.
- Login butonu islem sirasinda disabled olur ve `Giris yapiliyor...` gosterir.
- Login 500/auth_store_error durumunda eski token temizlenir.

## 4. Degisen dosyalar

- `backend/core/auth.py`
- `backend/routes/auth_routes.py`
- `frontend/js/app/auth.js`
- `frontend/js/app/api.js`
- `scripts/level1_40_18_auth_store_atomic_write_audit.py`
- `docs/LEVEL1_40_18_AUTH_STORE_ATOMIC_WRITE_AUDIT.json`
- `docs/LEVEL1_40_18_AUTH_STORE_ATOMIC_WRITE_AUDIT.md`
- `docs/PACKAGE_10_3_AUTH_STORE_ATOMIC_WRITE.md`
- `README.md`
- `todo.md`

## 5. Dokunulmayan kritik dosyalar

- `backend/auth_store.json`
- `backend/auth_store.json.tmp`
- `backend/binance_credentials_store.json`
- `backend/settings_store.json`
- `backend/shadow_store.json`
- `backend/rule_store.json`
- `backend/runtime_backups/*`
- `backend/services/*order*`
- `backend/services/*executor*`
- `backend/services/*binance*`
- `frontend/js/app/realTrade.js`
- `frontend/js/app/realApproval.js`
- `webhook_server.py`
- `deploy/*`

## 6. Test sonuclari

- `py -X pycache_prefix=.pycache_paket10_3 -m py_compile backend\core\auth.py backend\routes\auth_routes.py scripts\level1_40_18_auth_store_atomic_write_audit.py`: pass
- `py scripts\level1_40_16_auth_401_state_guard_audit.py`: pass, `status=ok`, `api_401_not_backend_offline=true`, `api_401_preserve_rules_present=true`
- `py scripts\level1_40_17_paper_lab_state_truth_audit.py`: pass, `status=ok`, `auto_paper_lab_no_api_ready_hard_block=true`, `api_bundle_preserve_existing_rules_present=true`
- `py scripts\level1_40_18_auth_store_atomic_write_audit.py`: pass, `status=ok`, `auth_store_static_tmp_absent=true`, `auth_store_unique_tmp_present=true`, `auth_store_lock_present=true`, `auth_store_atomic_replace_present=true`, `auth_store_write_error_handled=true`, `frontend_login_double_submit_guard_present=true`, `frontend_login_button_disabled_present=true`
- `py scripts\level1_40_07_frontend_api_inventory.py`: pass, `call_count=90`, `unique_base_path_count=72`
- `py scripts\level1_40_08_api_contract_diff.py --strict`: pass, `matched_call_count=90`, `missing_path_count=0`, `method_mismatch_count=0`
- `py scripts\level1_40_09_missing_endpoint_report.py`: pass, `true_blocker_count=0`, `parser_gap_or_false_positive_count=0`
- `py -c "import os, sys; os.environ['HMTSTC_DISABLE_RUNTIME_SCHEDULER']='1'; sys.path.insert(0, 'backend'); import main; print(main.health())"`: pass, `{'status': 'healthy'}`
- `node --check frontend\js\app\auth.js`: calistirilamadi, Node PATH'te yok. Bloklayici degil; 40.18 audit ve manuel kabul testi ile kontrol edildi.
- `node --check frontend\js\app\api.js`: calistirilamadi, Node PATH'te yok. Bloklayici degil; 40.18 audit ve manuel kabul testi ile kontrol edildi.

## 7. Manuel kabul testi

1. Login ekraninda giris butonuna hizli sekilde 5 kez basilir.
2. Network tarafinda en fazla 1 `/api/auth/login` istegi gorulur.
3. Sifre alaninda Enter ve hemen ardindan buton denenir.
4. UI takilmaz, login butonu islem sirasinda disabled kalir.
5. Backend logda `auth_store.json.tmp` FileNotFoundError gorulmez.
6. Login sonrasi dashboard/bundle 401 zinciri olusmaz.
7. Filtre/strateji secimi ve Auto Paper Lab stabil kalir.

## 8. Paket 11'e gecis karari

40.16, 40.17 ve 40.18 auditleri `ok` kaldigi surece Paket 11'e gecis uygundur.
