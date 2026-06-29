# Paket 10.6 Auth Restore Truth

## 1. Paket amaci

Paket 10.6, acilista localStorage token var diye kullanicinin dogrudan authenticated kabul edilmesini engeller. Token sadece restore adayi sayilir; auth kaynagi `/api/auth/me` cevabidir.

Bu paket rollback yapmaz. Paket 10.5 polling, heavy sync delay, bundle fallback ve rules hydration davranislari korunur. Binance, Futures, real-trade, order executor, Karabasan matematiği, Paper Lab kombinasyon matematiği ve strateji/filter karar mantigi degismedi.

## 2. Problem kaniti

Onceki frontend state baslangici:

- `auth: Boolean(localStorage.getItem("hmtstc_token"))`
- `init.js` icinde `auth=true` ise dogrudan `syncApiData()`

Bu modelde token gecerliligi bilinmeden dashboard/rules/settings sync baslayabiliyordu. Token yokken sync hic baslamiyor, token gecersizken 401 zinciriyle UI kirilgan hale geliyordu.

## 3. Yapilan degisiklikler

### State truth

- `auth` baslangicta her zaman `false`.
- `authRestorePending` token varligina gore baslar.
- `authRestoreChecked`, `authRestoreError` ve `authDiagnostics` alanlari eklendi.
- Token localStorage'dan okunur ama auth karari icin tek kaynak degildir.

### Startup gate

- `init.js` acilista `restoreAuth()` calistirir.
- Restore bitmeden polling sync baslamaz.
- Polling 30 saniye, `isUserEditing` ve `syncInProgress` guardlari korunur.

### Auth restore

`restoreAuth()` akisi:

1. Token yoksa login state'e doner ve sync baslatmaz.
2. Token varsa `/api/auth/me` cagrilir.
3. `/api/auth/me` 200 ise `auth=true` olur ve core sync `skipHeavySync: true` ile calisir.
4. 401/403 ise token temizlenir, restricted data korunarak login state'e alinir.
5. Network/timeout/502 gibi gecici hatada token hemen silinmez; login ekraninda net gecici hata gosterilir.

### Request izolasyonu

- `/api/auth/me` restore istegi `requestKind: "auth_restore"`, `preventGlobalAbort: true`, `timeoutMs: 10000` ile calisir.
- `syncApiData()` icinde `authRestorePending`, `no_token`, `auth_not_verified`, `force_password_change`, `sync_in_progress` block reason alanlari yazilir.
- Token degeri loglanmaz; sadece `tokenExists` tutulur.

## 4. Yeni audit

Yeni kalite kapisi:

- `scripts/level1_40_21_auth_restore_truth_audit.py`
- `docs/LEVEL1_40_21_AUTH_RESTORE_TRUTH_AUDIT.json`
- `docs/LEVEL1_40_21_AUTH_RESTORE_TRUTH_AUDIT.md`

40.21 audit su alanlari blocker yapar:

- State baslangicinda localStorage token auth truth degil.
- `authRestorePending`, `authRestoreChecked`, diagnostic alanlari var.
- Init restore gate var.
- `restoreAuth()` ve `/api/auth/me` korumali request var.
- 401/403 token temizler.
- Network hatasi tokeni hemen silmez.
- Login/logout restore truth alanlarini net set eder.
- `syncApiData()` auth restore pending durumunda bloklar.
- Paket 10.5 heavy sync guardlari korunur.
- 40.20 audit status `ok`.

## 5. Degisen dosyalar

- `frontend/js/app/state.js`
- `frontend/js/app/init.js`
- `frontend/js/app/auth.js`
- `frontend/js/app/api.js`
- `scripts/level1_40_20_live_startup_rules_hydration_audit.py`
- `scripts/level1_40_21_auth_restore_truth_audit.py`
- `docs/LEVEL1_40_20_LIVE_STARTUP_RULES_HYDRATION_AUDIT.json`
- `docs/LEVEL1_40_20_LIVE_STARTUP_RULES_HYDRATION_AUDIT.md`
- `docs/LEVEL1_40_21_AUTH_RESTORE_TRUTH_AUDIT.json`
- `docs/LEVEL1_40_21_AUTH_RESTORE_TRUTH_AUDIT.md`
- `docs/PACKAGE_10_6_AUTH_RESTORE_TRUTH.md`
- `README.md`
- `todo.md`

## 6. Dokunulmayan kritik dosyalar

Su kritik alanlara dokunulmadi:

- `backend/binance_credentials_store.json`
- `backend/settings_store.json`
- `backend/shadow_store.json`
- `backend/auth_store.json`
- `backend/services/*order*`
- `backend/services/*executor*`
- `backend/services/*binance*`
- `frontend/js/app/realTrade.js`
- `frontend/js/app/realApproval.js`
- `webhook_server.py`
- `deploy/*`

## 7. Test sonuclari

- `py -X pycache_prefix=.pycache_paket10_6 -m py_compile scripts\level1_40_21_auth_restore_truth_audit.py`: pass
- `py -X pycache_prefix=.pycache_paket10_6 -m py_compile scripts\level1_40_20_live_startup_rules_hydration_audit.py scripts\level1_40_21_auth_restore_truth_audit.py`: pass
- `py scripts\level1_40_20_live_startup_rules_hydration_audit.py`: pass, `status=ok`
- `py scripts\level1_40_21_auth_restore_truth_audit.py`: pass, `status=ok`, `state_auth_not_localstorage_truth=true`, `init_restore_gate_present=true`, `restore_auth_function_present=true`, `api_sync_auth_restore_guard_present=true`
- `py scripts\level1_40_07_frontend_api_inventory.py`: pass, `call_count=91`, `unique_base_path_count=72`
- `py scripts\level1_40_08_api_contract_diff.py --strict`: pass, `matched_call_count=91`, `missing_path_count=0`, `method_mismatch_count=0`
- `py scripts\level1_40_09_missing_endpoint_report.py`: pass, `true_blocker_count=0`, `parser_gap_or_false_positive_count=0`
- `node --check frontend\js\app\state.js`: calistirilamadi, Node PATH'te yok
- `node --check frontend\js\app\init.js`: calistirilamadi, Node PATH'te yok
- `node --check frontend\js\app\auth.js`: calistirilamadi, Node PATH'te yok
- `node --check frontend\js\app\api.js`: calistirilamadi, Node PATH'te yok

## 8. Canli kabul testi

1. Token yokken Ctrl+F5 yapilir; sync storm baslamaz ve login ekrani gelir.
2. Login olunca token yazilir, `auth=true`, `authRestoreChecked=true`, core sync calisir ve filtre/strateji gelir.
3. Token varken Ctrl+F5 yapilir; once `/api/auth/me`, sonra core sync calisir.
4. Gecersiz token ile Ctrl+F5 yapilir; `/api/auth/me` 401 doner, token temizlenir ve login ekrani gelir.
5. Auth restore network/502/timeout hatasinda token hemen silinmez; gecici hata mesaji gosterilir.
6. Logout 200 veya 401 olsa da state temizlenir ve tekrar login yapilabilir.
7. Console'da `502 Bad Gateway`, `AbortError: signal is aborted`, `Backend erişilemiyor`, `Login cevabı okunamadı` kalmamalidir.
8. Backend 15 dakika timeout/KILL yememelidir.

## 9. Paket 11'e gecis karari

Paket 11'e sadece 40.20 ve 40.21 auditleri `ok`, canli auth restore kabul testi basarili ve backend stabil kaldiktan sonra gecilebilir.
