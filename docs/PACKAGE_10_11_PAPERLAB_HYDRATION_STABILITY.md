# Paket 10.11 Paper Lab Hydration Stability

## 1. Paket amaci

Paket 10.11, Paket 10.10 sonrasi kalici Paper Lab status hidrasyonunun rules render ile yarismasini engeller.

Problem backend 500/502 degildir. Ama kisa zaman diliminde su isteklerin ayni anda fırlamasi UI'da gecici bos gorunme yaratabilir:

- `/api/dashboard/bundle`
- `/api/rules`
- `/api/rules/paper-lab/status`

Bu paket sadece hydration timing ve request coalescing davranisini duzeltir.

## 2. Korunan davranislar

Degistirilmedi:

- Paper Lab persistence store
- Paper Lab autonomous engine
- Dashboard active selection
- CoinFilter draft persistence
- Auth restore
- Heavy sync delay
- Trading logic
- Binance / order executor / Futures alanlari

## 3. Paper Lab status throttle

Yeni frontend state alanlari:

- `paperLabStatusLastFetchMs`
- `paperLabStatusFetchInProgress`
- `paperLabStatusMinIntervalMs = 60000`
- `paperLabStatusLoading`

Kural:

- Status fetch devam ediyorsa ikinci fetch baslamaz.
- Son fetch uzerinden 60 saniye gecmediyse yeni status fetch baslamaz.
- Paper Lab run sonrasi explicit `force=true` refresh kullanilabilir.

## 4. Bundle onceligi

Core sync once `/api/dashboard/bundle` dener.

Bundle basariliysa:

- `rules` bundle'dan hydrate edilir.
- `paper_lab_status` bundle'dan hydrate edilir.
- Ayrı `/api/rules/paper-lab/status` hemen cagrilmaz.

Bundle icinde `paper_lab_status` yoksa ve throttle izin verirse status endpoint sonradan, rules render'dan izole sekilde cagrilir.

## 5. Fallback coalescing

Bundle basarisizsa fallback core istekleri calisir.

Fallback icinde `/api/rules/paper-lab/status` artik ayni `Promise.allSettled` grubunda degildir. Once `/api/rules` gelir ve rules render korunur; Paper Lab status daha sonra throttle guard ile cagrilir.

## 6. Rules render stability

Paper Lab status hicbir durumda su alanlari temizlemez veya overwrite etmez:

- `HMTSTC_DATA.rules`
- `filters`
- `strategies`
- `selected_filter_ids`
- `selected_strategy_ids`
- `lastKnownRulesSelection`

Son basarili rules payload korunur. Bos/eksik/partial payload rules listesini temizlemez.

## 7. Stratejiler sayfasi

`Son Paper Lab Calismasi` paneli status loading durumunu kendi icinde gosterir:

- `Paper Lab sonucu yükleniyor...`

Bu loading state filtre/strateji listelerini veya rules render sonucunu etkilemez.

## 8. Yeni audit

Yeni kalite kapisi:

- `scripts/level1_40_26_paperlab_hydration_stability_audit.py`
- `docs/LEVEL1_40_26_PAPERLAB_HYDRATION_STABILITY_AUDIT.json`
- `docs/LEVEL1_40_26_PAPERLAB_HYDRATION_STABILITY_AUDIT.md`

40.26 blocker kontrolleri:

- `paper_lab_status_throttle_present`
- `paper_lab_status_in_progress_guard_present`
- `paper_lab_status_force_refresh_present`
- `bundle_paper_lab_status_preferred`
- `paper_lab_status_does_not_clear_rules`
- `rules_render_preserve_on_partial_payload`
- `strategies_panel_isolated_loading_present`
- `request_coalescing_present`
- 40.20-40.25 status `ok`

## 9. Degisen dosyalar

- `frontend/js/app/state.js`
- `frontend/js/app/api.js`
- `frontend/js/app/rules.js`
- `frontend/js/pages/strategies.js`
- `scripts/level1_40_26_paperlab_hydration_stability_audit.py`
- `docs/LEVEL1_40_26_PAPERLAB_HYDRATION_STABILITY_AUDIT.json`
- `docs/LEVEL1_40_26_PAPERLAB_HYDRATION_STABILITY_AUDIT.md`
- `docs/PACKAGE_10_11_PAPERLAB_HYDRATION_STABILITY.md`
- `README.md`
- `todo.md`

## 10. Test sonuclari

- `py -X pycache_prefix=.pycache_paket10_11 -m py_compile scripts\level1_40_26_paperlab_hydration_stability_audit.py`: pass
- `py scripts\level1_40_20_live_startup_rules_hydration_audit.py`: pass, `status=ok`
- `py scripts\level1_40_21_auth_restore_truth_audit.py`: pass, `status=ok`
- `py scripts\level1_40_22_coinfilter_rules_paperlab_audit.py`: pass, `status=ok`
- `py scripts\level1_40_23_rules_paperlab_independence_audit.py`: pass, `status=ok`
- `py scripts\level1_40_24_paperlab_autonomous_engine_audit.py`: pass, `status=ok`
- `py scripts\level1_40_25_paperlab_persistence_audit.py`: pass, `status=ok`
- `py scripts\level1_40_26_paperlab_hydration_stability_audit.py`: pass, `status=ok`, `paper_lab_status_throttle_present=true`, `paper_lab_status_in_progress_guard_present=true`, `bundle_paper_lab_status_preferred=true`, `request_coalescing_present=true`
- `py scripts\level1_40_08_api_contract_diff.py --strict`: pass, `matched_call_count=94`, `missing_path_count=0`, `method_mismatch_count=0`
- `py scripts\level1_40_09_missing_endpoint_report.py`: pass, `missing_path_count=0`, `method_mismatch_count=0`, `true_blocker_count=0`
- `node --check frontend\js\app\api.js`: calistirilamadi, Node PATH'te yok
- `node --check frontend\js\app\rules.js`: calistirilamadi, Node PATH'te yok
- `node --check frontend\js\pages\strategies.js`: calistirilamadi, Node PATH'te yok

## 11. Canli kabul testi

1. Ctrl+F5 yapilir.
2. Filtre/stratejiler bos yanip sonmemeli.
3. Paper Lab paneli gec yuklenirse sadece panel loading gosterir.
4. `/api/rules/paper-lab/status` surekli firlamaz.
5. `/api/rules`, `/api/rules/paper-lab/status`, `/api/dashboard/bundle` request storm olusturmaz.
6. Paper Lab calistirilir.
7. Run sonrasi panel guncellenir.
8. Dashboard secimleri ve rules listesi degismez.
9. Backend loglarda 500/502/timeout olmamalidir.

## 12. Paket 11'e gecis karari

Paket 11'e sadece 40.20-40.26 zinciri `ok` olduktan, status endpoint storm olusturmadigi canli loglarda gorulduktan ve runtime store git'e girmedigi dogrulandiktan sonra gecilebilir.
