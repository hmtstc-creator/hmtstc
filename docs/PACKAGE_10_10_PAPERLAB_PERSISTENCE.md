# Paket 10.10 Paper Lab Persistence

## 1. Paket amaci

Paket 10.10, Paper Lab sonucunu gecici frontend state olmaktan cikarip kalici backend runtime arastirma verisi yapar.

Korunan urun karari:

- Paper Lab sonucu `HMTSTC_APP.state` veya `HMTSTC_DATA` icindeki RAM cache'e bagli degildir.
- Paper Lab run kaydi backend restart, Ctrl+F5, deploy ve git pull sonrasi okunabilir kalir.
- Dashboard active rule selection ve Paper Lab kapsam bagimsizligi Paket 10.8 / 10.9 davranisi olarak korunur.

## 2. Kalici store

Yeni runtime store:

- `backend/paper_lab_store.json`

Kaynakta sadece sanitize example tutulur:

- `backend/paper_lab_store.example.json`

Runtime store git'e girmez:

- `.gitignore` icinde `backend/paper_lab_store.json`
- `.gitignore` icinde `backend/paper_lab_store.json.*`

## 3. Atomic write

Yeni servis:

- `backend/services/paper_lab_store.py`

Servis su guvenlik kurallarini uygular:

- `threading.RLock`
- unique tmp filename
- `os.replace`
- bozuk JSON durumunda corrupt backup
- eksik store durumunda bos ama gecerli schema
- kullanici basina son 20 run

## 4. Run persistence

Paper Lab basarili veya basarisiz her calismada run kaydi yazar.

Minimum alanlar:

- `run_id`
- `status`
- `started_at`
- `completed_at`
- `filter_ids`
- `strategy_ids`
- `filter_count`
- `strategy_count`
- `candidate_count`
- `accepted_combinations`
- `rejected_combinations`
- `model_count`
- `trigger`
- `source`
- `rules_fingerprint`
- `error_message`

Basarisiz calismalar `status=failed` ve `error_message` ile saklanir.

## 5. Rules fingerprint

`paper_lab_rules_fingerprint` enabled filtre ve strateji id listelerini siralayip sha256 uretir.

Amac:

- Yeni filtre/strateji yoksa onceki Paper Lab sonucu gecerli kabul edilebilir.
- Yeni filtre/strateji varsa Stratejiler sayfasi fingerprint mismatch uyarisi gosterir.

## 6. API ve hydration

Yeni endpoint:

- `GET /api/rules/paper-lab/status`

Dashboard bundle icine de ayni kalici durum eklenir:

- `paper_lab_status`

Frontend `applyPaperLabStatusPayload` ile su alanlari backend persistent store'dan hydrate eder:

- `HMTSTC_APP.state.lastPaperLabResult`
- `HMTSTC_APP.state.paperLabRun`
- `HMTSTC_DATA.paperLabStatus`

## 7. Stratejiler sayfasi

`Son Paper Lab Calismasi` paneli artik persistent `last_run` kaynagini kullanir.

Panelde gosterilen alanlar:

- Son run zamani
- Run id
- Durum
- Filter count
- Strategy count
- Candidate count
- Accepted / rejected count
- Model count
- Rules fingerprint match

Fingerprint farkliysa panelde su karar gorunur:

- `Bu Paper Lab sonucu mevcut filtre/strateji setinden once olusturuldu.`

## 8. Degisen dosyalar

- `.gitignore`
- `backend/paper_lab_store.example.json`
- `backend/services/paper_lab_store.py`
- `backend/services/rule_engine.py`
- `backend/routes/rule_routes.py`
- `backend/routes/dashboard_routes.py`
- `frontend/js/app/api.js`
- `frontend/js/app/rules.js`
- `frontend/js/pages/strategies.js`
- `scripts/level1_40_25_paperlab_persistence_audit.py`
- `docs/LEVEL1_40_25_PAPERLAB_PERSISTENCE_AUDIT.json`
- `docs/LEVEL1_40_25_PAPERLAB_PERSISTENCE_AUDIT.md`
- `docs/PACKAGE_10_10_PAPERLAB_PERSISTENCE.md`
- `README.md`
- `todo.md`

## 9. Dokunulmayan kritik dosyalar

- `backend/binance_credentials_store.json`
- `backend/auth_store.json`
- `backend/settings_store.json`
- `backend/shadow_store.json`
- `backend/services/*order*`
- `backend/services/*executor*`
- `backend/services/*binance*`
- `frontend/js/app/realTrade.js`
- `frontend/js/app/realApproval.js`
- `webhook_server.py`
- `deploy/*`

## 10. Test sonuclari

- `py -X pycache_prefix=.pycache_paket10_10 -m py_compile backend\services\paper_lab_store.py backend\services\rule_engine.py backend\routes\rule_routes.py backend\routes\dashboard_routes.py scripts\level1_40_25_paperlab_persistence_audit.py`: pass
- `py scripts\level1_40_20_live_startup_rules_hydration_audit.py`: pass, `status=ok`
- `py scripts\level1_40_21_auth_restore_truth_audit.py`: pass, `status=ok`
- `py scripts\level1_40_22_coinfilter_rules_paperlab_audit.py`: pass, `status=ok`, `rules_save_end_to_end_selection_proof_present=true`
- `py scripts\level1_40_23_rules_paperlab_independence_audit.py`: pass, `status=ok`
- `py scripts\level1_40_24_paperlab_autonomous_engine_audit.py`: pass, `status=ok`
- `py scripts\level1_40_25_paperlab_persistence_audit.py`: pass, `status=ok`, `paper_lab_store_atomic_write_present=true`, `paper_lab_run_recorded_on_success=true`, `paper_lab_run_recorded_on_failure=true`, `frontend_hydrates_paperlab_from_backend=true`, `strategies_page_uses_persistent_last_run=true`
- `py scripts\level1_40_06_api_route_inventory.py`: pass, `route_count=893`
- `py scripts\level1_40_07_frontend_api_inventory.py`: pass, `call_count=94`, `unique_base_path_count=74`
- `py scripts\level1_40_08_api_contract_diff.py --strict`: pass, `matched_call_count=94`, `missing_path_count=0`, `method_mismatch_count=0`
- `py scripts\level1_40_09_missing_endpoint_report.py`: pass, `missing_path_count=0`, `method_mismatch_count=0`, `true_blocker_count=0`
- `py scripts\level1_40_10_mutating_endpoint_safety_audit.py`: pass, `status=ok`, `mutating_call_count=51`, `unclassified_mutating_count=0`
- `py -c "import os, sys; os.environ['HMTSTC_DISABLE_RUNTIME_SCHEDULER']='1'; sys.path.insert(0, 'backend'); import main; print(main.health())"`: pass, `{'status': 'healthy'}`
- `git diff --check`: pass, sadece CRLF uyarilari
- `node --check frontend\js\app\api.js`: calistirilamadi, Node PATH'te yok
- `node --check frontend\js\app\rules.js`: calistirilamadi, Node PATH'te yok
- `node --check frontend\js\pages\strategies.js`: calistirilamadi, Node PATH'te yok

## 11. Canli kabul testi

1. Paper Lab calistirilir.
2. Sonuc gorunur.
3. Run id ve candidate count gorunur.
4. Ctrl+F5 yapilir.
5. Son Paper Lab sonucu hala gorunur.
6. Backend restart edilir.
7. Ctrl+F5 sonrasi son Paper Lab sonucu hala gorunur.
8. Git pull/deploy sonrasi backend restart edilir.
9. Son Paper Lab sonucu hala gorunur.
10. Yeni filtre/strateji eklenmediyse `last_run_matches_current_rules=true` olur.
11. Yeni filtre/strateji eklendiyse Stratejiler sayfasi fingerprint mismatch uyarisi gosterir.

## 12. Paket 11'e gecis karari

Paket 11'e sadece 40.20, 40.21, 40.22, 40.23, 40.24 ve 40.25 auditleri `ok` olduktan ve runtime store git'e girmedigi dogrulandiktan sonra gecilebilir.
