# Paket 10.7 CoinFilter Rules PaperLab

## 1. Paket amaci

Paket 10.7, canli testte gorulen uc frontend davranisini duzeltir:

- CoinFilter input degerlerinin render/sync ile eski backend datasina donmesi.
- Dashboard filtre/strateji secimlerinin Paper Lab sonrasi tumu secili hale gelmesi.
- Paper Lab calismasinin Stratejiler sayfasinda gorunur durum/rapor olarak kalmamasi.

Rollback yapilmadi. Paket 10.5 ve 10.6 startup/auth restore guardlari korundu. Binance, Futures, real-trade, order executor, Karabasan matematiği, Paper Lab kombinasyon matematiği ve strateji/filter karar mantigi degismedi.

## 2. CoinFilter draft persistence

CoinFilter inputlari artik dogrudan backend `HMTSTC_DATA.settings` kaynagina bagli degil.

Eklenen davranis:

- Sayfa acilinca backend settings verisinden `coinFilterDraft` olusturulur.
- Kullanici input degistirdiginde sadece draft guncellenir.
- Polling/render sirasinda dirty draft eski backend datasiyla overwrite edilmez.
- Save basarili olursa draft backend state'e commit edilir.
- Save hata/abort alirsa draft korunur.
- Save button `type="button"` ve handler `event.preventDefault()` kullanir.
- Save sonrasi scroll pozisyonu korunur.
- Save sonrasi immediate `syncHeavyApiData()` calismaz.

## 3. Rules selection integrity

Dashboard checkbox mantigi su sekilde netlestirildi:

- Backend `selected_filter_ids` / `selected_strategy_ids` explicit gelirse birebir kullanilir.
- Backend selected alanlari eksikse `lastKnownRulesSelection` kullanilir.
- Son bilinen secim de yoksa bos secim korunur.
- Bos selected id listesi artik "hepsini sec" anlamina gelmez.
- Paper Lab activate basarili oldugunda selected id'ler ve last-known selection birlikte guncellenir.
- Empty/partial rules payload son basarili liste ve secim bilgisini korur.

## 4. Paper Lab visibility

Paper Lab activate ve auto Paper Lab sonucunda:

- `HMTSTC_DATA.paperLabStatus`
- `HMTSTC_APP.state.lastPaperLabResult`

alanlari guncellenir.

Stratejiler sayfasina `Son Paper Lab Çalışması` paneli eklendi. Bu panel heavy reports gecikse bile son backend response durumunu, secili filtre/strateji sayisini, kabul/red kombinasyon sayisini ve model sayisini gosterir.

## 5. Rules Save End-to-End Selection Proof

40.22 icine ek proof zinciri eklendi. Dashboard filtre/strateji secimleri su noktalarda ayni ID seti olarak kanitlanir:

- Kullanici save payload'i: `selected_filter_ids` / `selected_strategy_ids`
- Backend response / store datası: `result.selected_filter_ids` / `result.selected_strategy_ids`
- Dashboard render checked state: `dashboardRenderedRuleSelection`
- Paper Lab sonrasi dashboard render checked state: `rulesSelectionProof`

Bu zincir yoksa veya statik kanit eksikse 40.22 audit `blocker` doner.

## 6. Yeni audit

Yeni kalite kapisi:

- `scripts/level1_40_22_coinfilter_rules_paperlab_audit.py`
- `docs/LEVEL1_40_22_COINFILTER_RULES_PAPERLAB_AUDIT.json`
- `docs/LEVEL1_40_22_COINFILTER_RULES_PAPERLAB_AUDIT.md`

40.22 audit su alanlari blocker yapar:

- CoinFilter local draft state
- Save submit engeli ve scroll koruma
- Save sonrasi immediate heavy sync olmamasi
- Numeric conversion ve core refresh
- Dashboard default-all selected mantiginin olmamasi
- Last-known rules selection korumasi
- Rules save end-to-end selection proof
- Paper Lab success state
- Stratejiler sayfasi Paper Lab visibility
- 40.20 ve 40.21 audit status `ok`

## 7. Degisen dosyalar

- `frontend/js/app/api.js`
- `frontend/js/app/rules.js`
- `frontend/js/app/state.js`
- `frontend/js/pages/coinFilter.js`
- `frontend/js/pages/dashboard.js`
- `frontend/js/pages/strategies.js`
- `scripts/level1_40_22_coinfilter_rules_paperlab_audit.py`
- `docs/LEVEL1_40_20_LIVE_STARTUP_RULES_HYDRATION_AUDIT.json`
- `docs/LEVEL1_40_21_AUTH_RESTORE_TRUTH_AUDIT.json`
- `docs/LEVEL1_40_22_COINFILTER_RULES_PAPERLAB_AUDIT.json`
- `docs/LEVEL1_40_22_COINFILTER_RULES_PAPERLAB_AUDIT.md`
- `docs/PACKAGE_10_7_COINFILTER_RULES_PAPERLAB.md`
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

- `py -X pycache_prefix=.pycache_paket10_7 -m py_compile scripts\level1_40_22_coinfilter_rules_paperlab_audit.py`: pass
- `py scripts\level1_40_20_live_startup_rules_hydration_audit.py`: pass, `status=ok`
- `py scripts\level1_40_21_auth_restore_truth_audit.py`: pass, `status=ok`
- `py scripts\level1_40_22_coinfilter_rules_paperlab_audit.py`: pass, `status=ok`, `coinfilter_draft_state_present=true`, `dashboard_no_default_all_selected=true`, `paper_lab_success_state_present=true`, `strategies_paper_lab_visibility_present=true`, `rules_save_end_to_end_selection_proof_present=true`
- `py scripts\level1_40_07_frontend_api_inventory.py`: pass, `call_count=92`, `unique_base_path_count=72`
- `py scripts\level1_40_08_api_contract_diff.py --strict`: pass, `matched_call_count=92`, `missing_path_count=0`, `method_mismatch_count=0`
- `py scripts\level1_40_09_missing_endpoint_report.py`: pass, `true_blocker_count=0`, `parser_gap_or_false_positive_count=0`
- `node --check frontend\js\pages\coinFilter.js`: calistirilamadi, Node PATH'te yok
- `node --check frontend\js\app\rules.js`: calistirilamadi, Node PATH'te yok
- `node --check frontend\js\pages\dashboard.js`: calistirilamadi, Node PATH'te yok
- `node --check frontend\js\app\api.js`: calistirilamadi, Node PATH'te yok

## 10. Canli kabul testi

### CoinFilter

1. CoinFilter ekraninda numeric deger degistirilir.
2. Sayfa yukari ziplamadan kaydedilir.
3. Deger eskiye donmez.
4. Ctrl+F5 sonrasi deger korunur.

### Rules

1. Dashboardda sadece secili filtre/stratejiler isaretlenir.
2. Kaydedilir ve Ctrl+F5 yapilir.
3. Sadece secilenler secili kalir.
4. Paper Lab calistiktan sonra tumu otomatik secili hale gelmez.
5. Save payload, backend response, dashboard checked render ve Paper Lab sonrasi checked render ayni `selected_filter_ids` / `selected_strategy_ids` setini gostermelidir.

### Paper Lab

1. Kombinasyon Lab baslatilir.
2. Kombinasyon sayisi gorunur.
3. Stratejiler sayfasinda `Son Paper Lab Çalışması` paneli gorunur.
4. Refresh sonrasi bilgi kaybolmaz.

## 11. Paket 11'e gecis karari

Paket 11'e sadece 40.20, 40.21 ve 40.22 auditleri `ok`, canli CoinFilter persistence testi, rules selection integrity testi ve Paper Lab visibility testi basarili olduktan sonra gecilebilir.
