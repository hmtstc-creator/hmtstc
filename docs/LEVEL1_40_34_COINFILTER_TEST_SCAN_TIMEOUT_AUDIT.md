# Level1 40.34 CoinFilter Test Scan Timeout Audit

## Ozet

- Durum: `ok`
- Test scan deep analysis kapali: `evet`
- Runtime analyze_symbol call count: `0`
- Lightweight mode: `coinfilter_lightweight_test_scan`
- Onceki 40.20-40.33 zinciri: `evet`

## Kontroller

- test_scan_uses_deep_analysis_false: `evet`
- scan_market_accepts_deep_analysis_parameter: `evet`
- deep_analysis_false_skips_analyze_symbol: `evet`
- deep_analysis_false_skips_fetch_klines: `evet`
- test_scan_response_has_test_scan_true: `evet`
- test_scan_response_has_pipeline: `evet`
- diagnostics_deep_analysis_disabled: `evet`
- diagnostics_deep_analysis_limit_zero: `evet`
- diagnostics_deep_analyzed_count_zero: `evet`
- diagnostics_lightweight_mode_present: `evet`
- frontend_test_scan_loading_present: `evet`
- frontend_timeout_message_present: `evet`
- previous_40_20_to_40_33_status_ok: `evet`

## Blocker Listesi

Blocker yok.

## Sonuc

CoinFilter test scan lightweight kalite kapisi temiz.
