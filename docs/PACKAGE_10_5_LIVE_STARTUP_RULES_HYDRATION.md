# Paket 10.5 Live Startup Rules Hydration

## 1. Paket amaci

Paket 10.5, canlı ortamda Ctrl+F5 / login sonrasında filtre ve strateji listelerinin boş kalmasını, login/logout akışlarının ağır sync ile çakışmasını ve heavy endpointlerin backend CPU/RAM yükünü artırmasını azaltır.

Bu paket rollback yapmaz ve yeni özellik eklemez. Binance, Futures, real-trade, order executor, Karabasan matematiği, Paper Lab kombinasyon matematiği ve strateji/filter karar mantığı değişmedi.

## 2. Problem kaniti

Canlı loglarda tekil endpointler 200 dönebilirken servis timeout/KILL yiyordu:

- `GET /api/rules 200 OK`
- `GET /api/settings 200 OK`
- `GET /api/dashboard/bundle 200 OK`
- `POST /api/auth/login 200 OK`
- servis tarafında `status=9/KILL`, `timeout`, yüksek CPU/RAM

Kök sebep endpoint kontratı değil, frontend polling + heavy sync storm + rules hydration bağımlılığı olarak değerlendirildi.

## 3. Yapilan degisiklikler

### Main polling

- `frontend/js/app/init.js` polling aralığı 30 saniyede tutuldu.
- Auth yoksa, kullanıcı editliyorsa veya `syncInProgress=true` ise yeni sync başlamaz.

### Heavy sync erteleme

- `syncHeavyApiData` ilk startup/login sonrası 120 saniye ertelenir.
- Heavy sync aralığı 300000 ms, yani 5 dakika.
- Heavy sync hatası `apiReady=false` veya `apiSyncReady=false` yapmaz.
- Heavy hata sadece `systemStatus.heavy_status` ve `heavy_message` alanlarına yazılır.

### Bundle fallback ve rules hydration

- `/api/dashboard/bundle` başarısız olursa core fallback çağrıları çalışır.
- `/api/rules` ve `/api/settings` başarılıysa `apiReady/apiSyncReady` true kalabilir.
- Bundle başarısızlığı `systemStatus.bundle_status="degraded"` olarak görünür.
- Rules payload güvenli değilse son başarılı liste korunur.

### Login/logout izolasyonu

- Login/logout istekleri `requestKind: "mutation"`, `preventGlobalAbort: true`, `timeoutMs: 15000` ile çalışır.
- Login başarılı olunca core sync `skipHeavySync: true` ile yapılır.
- Login sonrası heavy sync hemen tetiklenmez; startup delay guardına kalır.
- Logout 401 toleransı korunur.

### Save sonrası heavy sync

- CoinFilter save sonrası doğrudan `syncHeavyApiData()` çağrısı kaldırıldı.
- Rules/Paper Lab success sonrası core sync `skipHeavySync: true` ile çalışır.
- Paper Lab success state refresh hatasıyla silinmez.

## 4. Yeni audit

Yeni kalite kapısı:

- `scripts/level1_40_20_live_startup_rules_hydration_audit.py`
- `docs/LEVEL1_40_20_LIVE_STARTUP_RULES_HYDRATION_AUDIT.json`
- `docs/LEVEL1_40_20_LIVE_STARTUP_RULES_HYDRATION_AUDIT.md`

40.20 audit şu alanları blocker yapar:

- 30 sn polling ve 5 sn polling yokluğu
- polling guardları
- 120 sn heavy startup delay
- 5 dk heavy interval
- heavy sync'in core ready state'i bozmaması
- bundle timeout fallback
- rules hydration preserve
- CoinFilter save sonrası immediate heavy sync olmaması
- login/logout protected mutation
- rules save sonrası immediate heavy sync olmaması
- 40.19 audit status `ok`

## 5. Degisen dosyalar

- `frontend/js/app/init.js`
- `frontend/js/app/api.js`
- `frontend/js/app/auth.js`
- `frontend/js/app/rules.js`
- `frontend/js/pages/coinFilter.js`
- `frontend/js/pages/dashboard.js`
- `scripts/level1_40_20_live_startup_rules_hydration_audit.py`
- `docs/LEVEL1_40_19_MUTATION_ABORT_ISOLATION_AUDIT.json`
- `docs/LEVEL1_40_19_MUTATION_ABORT_ISOLATION_AUDIT.md`
- `docs/LEVEL1_40_20_LIVE_STARTUP_RULES_HYDRATION_AUDIT.json`
- `docs/LEVEL1_40_20_LIVE_STARTUP_RULES_HYDRATION_AUDIT.md`
- `docs/PACKAGE_10_5_LIVE_STARTUP_RULES_HYDRATION.md`
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

- `py -X pycache_prefix=.pycache_paket10_5 -m py_compile scripts\level1_40_20_live_startup_rules_hydration_audit.py`: pass
- `py scripts\level1_40_20_live_startup_rules_hydration_audit.py`: pass, `status=ok`, `polling_30000_present=true`, `heavy_startup_delay_present=true`, `heavy_interval_300000_present=true`, `bundle_timeout_fallback_present=true`, `coinfilter_save_no_immediate_heavy_sync=true`, `auth_login_logout_protected_mutation=true`
- `py scripts\level1_40_19_mutation_abort_isolation_audit.py`: pass, `status=ok`
- `py scripts\level1_40_07_frontend_api_inventory.py`: pass, `call_count=90`, `unique_base_path_count=72`
- `py scripts\level1_40_08_api_contract_diff.py --strict`: pass, `matched_call_count=90`, `missing_path_count=0`, `method_mismatch_count=0`
- `py scripts\level1_40_09_missing_endpoint_report.py`: pass, `true_blocker_count=0`, `parser_gap_or_false_positive_count=0`
- `node --check frontend\js\app\api.js`: calistirilamadi, Node PATH'te yok
- `node --check frontend\js\app\auth.js`: calistirilamadi, Node PATH'te yok
- `node --check frontend\js\app\rules.js`: calistirilamadi, Node PATH'te yok
- `node --check frontend\js\pages\coinFilter.js`: calistirilamadi, Node PATH'te yok
- `node --check frontend\js\app\init.js`: calistirilamadi, Node PATH'te yok

## 8. Canli kabul testi

1. Ctrl+F5 sonrası login durumu doğru gelmeli.
2. Filtre listesi görünmeli.
3. Strateji listesi görünmeli.
4. CoinFilter save çalışmalı.
5. Rules save çalışmalı.
6. Paper Lab otomatik oluştur çalışmalı.
7. Logout ve tekrar login çalışmalı.
8. Console’da `AbortError: signal is aborted`, `502 Bad Gateway`, `Backend erişilemiyor`, `Login cevabı okunamadı` kalmamalı.
9. Backend servis 15 dakika kullanımda timeout/KILL yememeli.
10. Nginx error log içinde yeni upstream timeout / bad gateway olmamalı.

## 9. Paket 11'e gecis karari

Paket 11'e sadece 40.20 audit `ok`, canlı Ctrl+F5 rules hydration testi başarılı ve backend 15 dakika timeout/KILL yemeden stabil kaldıktan sonra geçilebilir.
