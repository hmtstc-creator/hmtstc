# Paket 10.19 CoinFilter Test Scan Timeout Fix

## 1. Paket amaci

Paket 10.19, `/api/bot/coinfilter-test-scan` endpointinin deep teknik analiz nedeniyle Nginx 504 timeout'a dusmesini engeller.

Test scan artik yalnizca Binance 24h ticker verisi ve lightweight CoinFilter analizini kullanir. Normal bot tick teknik analiz davranisi korunur.

## 2. Backend ayrimi

`scan_market` yeni opsiyon alir:

```python
def scan_market(settings: dict, limit: int = 1000, *, deep_analysis: bool = True) -> dict:
```

- Normal bot scan: `deep_analysis=True`
- CoinFilter test scan: `deep_analysis=False`

Lightweight test scan icinde `analyze_symbol`, `fetch_klines`, strategy, Karabasan, risk ve execution calismaz.

## 3. Diagnostics contract

Test scan response:

```json
{
  "test_scan": true,
  "scan_diagnostics": {
    "mode": "coinfilter_lightweight_test_scan",
    "deep_analysis_enabled": false,
    "deep_analysis_limit": 0,
    "deep_analyzed_count": 0
  }
}
```

Paket 10.18 pipeline contract'i korunur.

## 4. Frontend davranisi

Test scan devam ederken buton disable olur ve `Test scan çalışıyor...` gosterir.

Timeout veya HTTP 504 durumunda:

`Test scan zaman aşımına uğradı. Deep analiz kapalı olmalı; backend kontrol edin.`

mesaji gosterilir.

## 5. Yeni audit

- `scripts/level1_40_34_coinfilter_test_scan_timeout_audit.py`
- `docs/LEVEL1_40_34_COINFILTER_TEST_SCAN_TIMEOUT_AUDIT.json`
- `docs/LEVEL1_40_34_COINFILTER_TEST_SCAN_TIMEOUT_AUDIT.md`

Audit statik contract kontrollerine ek olarak lightweight runtime probe calistirir. Probe, `analyze_symbol` cagirilirsa hata vererek test scan yolunun teknik analize girmedigini kanitlar.

## 6. Degisen dosyalar

- `backend/services/analysis_service.py`
- `backend/services/bot_service.py`
- `backend/routes/bot_routes.py`
- `frontend/js/pages/coinFilter.js`
- `scripts/level1_40_34_coinfilter_test_scan_timeout_audit.py`
- `docs/LEVEL1_40_34_COINFILTER_TEST_SCAN_TIMEOUT_AUDIT.json`
- `docs/LEVEL1_40_34_COINFILTER_TEST_SCAN_TIMEOUT_AUDIT.md`
- `docs/PACKAGE_10_19_COINFILTER_TEST_SCAN_TIMEOUT_FIX.md`
- `README.md`
- `todo.md`

## 7. Test sonuclari

- `py -X pycache_prefix=.pycache_paket10_19 -m py_compile backend\services\analysis_service.py backend\services\bot_service.py backend\routes\bot_routes.py scripts\level1_40_34_coinfilter_test_scan_timeout_audit.py`: pass
- `py -c "import sys; sys.path.insert(0, 'backend'); import main; print('backend import ok')"`: pass, `backend import ok`
- `py scripts\level1_40_34_coinfilter_test_scan_timeout_audit.py`: pass, `status=ok`, `test_scan_uses_deep_analysis_false=true`, `deep_analysis_false_skips_analyze_symbol=true`, `diagnostics_deep_analysis_disabled=true`, `previous_40_20_to_40_33_status_ok=true`
- 40.34 runtime probe: pass, `analyze_calls=0`, `mode=coinfilter_lightweight_test_scan`, `deep_analysis_limit=0`, `deep_analyzed_count=0`
- `py scripts\level1_40_33_coinfilter_final_pipeline_audit.py`: pass, `status=ok`
- `py scripts\level1_40_32_bot_restore_first_tick_audit.py`: pass, `status=ok`
- `py scripts\level1_40_31_bot_restore_real_loop_audit.py`: pass, `status=ok`
- `py scripts\level1_40_30_bot_runtime_heartbeat_truth_audit.py`: pass, `status=ok`
- `py scripts\level1_40_29_coinfilter_persistence_and_8h_report_audit.py`: pass, `status=ok`
- `py scripts\level1_40_09_missing_endpoint_report.py`: pass, `missing_path_count=0`, `method_mismatch_count=0`, `true_blocker_count=0`, `parser_gap_or_false_positive_count=0`
- `py scripts\level1_40_08_api_contract_diff.py --strict`: pass, `matched_call_count=94`, `missing_path_count=0`, `method_mismatch_count=0`
- Node REPL `vm.Script` parse kontrolu: pass, `frontend/js/pages/coinFilter.js`

Canli Binance ve Nginx sure hedefleri yerel statik/runtime probe ile olculemez; deploy sonrasi kabul adiminda dogrulanmalidir.

## 8. Canli kabul

Deploy ve backend restart sonrasi:

- `limit=20` istegi hedef olarak 5 saniyeden kisa surmeli.
- `limit=1000` istegi hedef olarak 20 saniyeden kisa surmeli.
- Her iki istek HTTP 200 donmeli.
- `test_scan=true` olmali.
- `deep_analysis_enabled=false` olmali.
- `deep_analyzed_count=0` olmali.
- Pipeline icindeki strategy, Karabasan, risk ve execution `not_run_in_coinfilter_test` olmali.

## 9. Paket 11'e gecis karari

Paket 11'e sadece 40.20-40.34 audit zinciri `ok` olduktan ve canli limit=20/1000 test scan istekleri 504 vermeden tamamlandiktan sonra gecilebilir.
