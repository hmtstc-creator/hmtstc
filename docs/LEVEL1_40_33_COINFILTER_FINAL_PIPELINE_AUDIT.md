# Level1 40.33 CoinFilter Final Pipeline Audit

## Ozet

- Durum: `blocker`
- Rule envanteri yok: `evet`
- Strategy envanteri yok: `evet`
- Test scan endpoint: `evet`
- Pipeline contract: `evet`

## Kontroller

- coinfilter_page_no_active_filter_inventory: `evet`
- coinfilter_page_no_active_strategy_inventory: `evet`
- coinfilter_main_table_no_readonly_fixed_guard_rows: `evet`
- frontend_default_has_min_quote_volume: `evet`
- frontend_default_has_min_trade_count: `evet`
- backend_default_has_min_quote_volume: `evet`
- backend_default_has_min_trade_count: `evet`
- normalize_coinfilter_keeps_min_quote_volume: `evet`
- normalize_coinfilter_keeps_min_trade_count: `evet`
- coinfilter_test_scan_endpoint_present: `evet`
- test_scan_does_not_require_bot_running: `evet`
- test_scan_response_has_test_scan_true: `hayir`
- test_scan_response_has_pipeline: `hayir`
- pipeline_has_all_contract_sections: `evet`
- coinfilter_page_has_new_funnel: `evet`
- coinfilter_page_has_test_scan_button: `evet`
- excluded_symbols_textarea_and_normalize_present: `evet`
- previous_40_20_to_40_32_status_ok: `evet`

## Blocker Listesi

- BLOCKER: test_scan_response_has_test_scan_true=false
- BLOCKER: test_scan_response_has_pipeline=false

## Sonuc

CoinFilter final pipeline kalite kapisi blocker durumunda.
