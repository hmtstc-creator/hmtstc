# Paket 10.4 Mutation Abort Isolation

## 1. Paket amaci

Paket 10.4, sync firtinasi ve agir endpoint timeoutlari sirasinda CoinFilter, Rules ve Paper Lab kayit isteklerinin yanlis `AbortError` etkisiyle global Backend API hatasina donmesini engeller.

Bu paket yeni trade davranisi eklemez. Binance, Futures, real-trade, order executor, Karabasan matematiği, Paper Lab kombinasyon matematiği ve strateji/filter karar mantigi degismedi.

## 2. Request tipleri

`frontend/js/app/api.js` icinde API istekleri su siniflara ayrildi:

- `core_read`
- `heavy_read`
- `mutation`
- `audit_best_effort`

`AbortError` artik `request_aborted` olarak siniflandirilir. `request_aborted`, mutation, heavy read ve audit best-effort hatalari Backend API durumunu kirmiziya cekmez.

## 3. Protected mutation akislari

Su akislarda `requestKind: "mutation"`, `preventGlobalAbort: true` ve mutation timeout kullanilir:

- CoinFilter `/api/settings` kaydi
- Dashboard bot kontrol tercihi `/api/settings` kaydi
- Rule get/save/delete akislari
- Paper Lab `/api/rules/activate-paper-lab`
- Auto Paper Lab `/api/rules/auto-paper-lab`
- Bulk rule normalize `/api/rules/save`

Abort durumunda form/draft/listeler korunur ve kullaniciya lokal "Istek iptal edildi; tekrar dene" mesaji verilir.

## 4. Sync ve agir endpoint izolasyonu

`syncApiData` zaten calisirken ikinci sync baslatmaz ve `false` doner. Agir endpointler `syncHeavyApiData` icinde ayri `heavySyncInProgress` guard'i ile calisir.

Agir endpointler Backend API global durumunu bozmaz:

- `/api/models/reports`
- `/api/intelligence/*`
- `/api/performance`
- `/api/binance/market`
- `/api/audit`

Timeout durumunda Dashboard `Ağır Analiz` veya `Audit` satirinda modül bazli uyari gorunur.

## 5. Dashboard status truth

Dashboard sistem durum seridi su ayrimi gosterir:

- Backend API
- Oturum
- Ağır Analiz
- Audit
- Rules
- Bot Durumu
- Karabasan
- Paper Lab
- Rule Store
- Binance API

Backend API karari core endpoint ve `last_api_request_kind=core_read` uzerinden verilir. `request_aborted`, audit abort ve heavy timeout global Backend API kirmizi sebebi degildir.

## 6. Yeni audit

Yeni kalite kapisi:

- `scripts/level1_40_19_mutation_abort_isolation_audit.py`
- `docs/LEVEL1_40_19_MUTATION_ABORT_ISOLATION_AUDIT.json`
- `docs/LEVEL1_40_19_MUTATION_ABORT_ISOLATION_AUDIT.md`

40.19 audit su kontrolleri blocker yapar:

- `request_aborted` siniflandirmasi
- mutation `preventGlobalAbort` destegi
- sync overlap guard
- heavy endpoint izolasyonu
- audit best-effort abort handling
- CoinFilter save protected mutation
- Rules/Paper Lab protected mutation
- Dashboard Backend API core status truth
- `request_aborted` backend offline degil
- 40.16 / 40.17 / 40.18 audit status `ok`

## 7. Degisen dosyalar

- `frontend/js/app/api.js`
- `frontend/js/app/audit.js`
- `frontend/js/app/rules.js`
- `frontend/js/pages/coinFilter.js`
- `frontend/js/pages/dashboard.js`
- `scripts/level1_40_17_paper_lab_state_truth_audit.py`
- `scripts/level1_40_19_mutation_abort_isolation_audit.py`
- `docs/LEVEL1_40_17_PAPER_LAB_STATE_TRUTH_AUDIT.json`
- `docs/LEVEL1_40_17_PAPER_LAB_STATE_TRUTH_AUDIT.md`
- `docs/LEVEL1_40_19_MUTATION_ABORT_ISOLATION_AUDIT.json`
- `docs/LEVEL1_40_19_MUTATION_ABORT_ISOLATION_AUDIT.md`
- `docs/PACKAGE_10_4_MUTATION_ABORT_ISOLATION.md`
- `README.md`
- `todo.md`

## 8. Dokunulmayan kritik dosyalar

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

## 9. Test sonuclari

- `py -X pycache_prefix=.pycache_paket10_4 -m py_compile scripts\level1_40_19_mutation_abort_isolation_audit.py`: pass
- `py scripts\level1_40_16_auth_401_state_guard_audit.py`: pass, `status=ok`
- `py scripts\level1_40_17_paper_lab_state_truth_audit.py`: pass, `status=ok`
- `py scripts\level1_40_18_auth_store_atomic_write_audit.py`: pass, `status=ok`
- `py scripts\level1_40_19_mutation_abort_isolation_audit.py`: pass, `status=ok`, `mutation_prevent_global_abort=true`, `coinfilter_save_protected=true`, `rules_save_protected=true`, `audit_best_effort_abort=true`, `heavy_endpoints_isolated=true`, `request_aborted_not_backend_offline=true`
- `py scripts\level1_40_07_frontend_api_inventory.py`: pass, `call_count=90`, `unique_base_path_count=72`
- `py scripts\level1_40_08_api_contract_diff.py --strict`: pass, `matched_call_count=90`, `missing_path_count=0`, `method_mismatch_count=0`
- `py scripts\level1_40_09_missing_endpoint_report.py`: pass, `true_blocker_count=0`, `parser_gap_or_false_positive_count=0`
- `node --check frontend\js\app\api.js`: calistirilamadi, Node PATH'te yok
- `node --check frontend\js\app\rules.js`: calistirilamadi, Node PATH'te yok
- `node --check frontend\js\pages\dashboard.js`: calistirilamadi, Node PATH'te yok
- Node REPL `new Function` parse denemesi: calistirilamadi, mevcut REPL context'i string code generation'i engelliyor

## 10. Manuel kabul testi

1. Ctrl + F5 ile Dashboard acilir.
2. Login olunur.
3. `Backend API` online ve `Oturum` gecerli gorunur.
4. CoinFilter sayfasinda bir deger degistirilip kaydedilir.
5. Kayit sirasinda buton disabled olur, ikinci tiklama baslamaz.
6. Console'da CoinFilter save icin global Backend API kirmizi yapan AbortError gorulmez.
7. Dashboard filtre/strateji secimi kaydedilir.
8. Paper Lab otomatik olusturulur.
9. Audit yazimi abort olsa bile Backend API kirmizi olmaz; Audit satiri uyari verebilir.
10. Agir analiz timeout olsa bile Backend API kirmizi olmaz; Ağır Analiz satiri modül uyarisina doner.
11. 5 dakika beklenir; Backend API yesil/kirmizi ziplama yapmaz.

## 11. Paket 11'e gecis karari

40.16-40.19 audit zinciri `ok` kaldigi, strict contract diff temiz oldugu ve canli kabul testi tamamlandigi surece Paket 11'e gecis uygundur.
