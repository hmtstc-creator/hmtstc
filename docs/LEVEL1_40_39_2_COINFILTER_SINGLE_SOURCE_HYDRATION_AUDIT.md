# Level1 40.39.2 CoinFilter Single Source Hydration Audit

- Durum: `ok`
- Amaç: CoinFilter ve Dashboard açılışta cached `last_scan` verisini tek kaynak olarak okusun; test scan manuel kalsın; dashboard bundle ağır rule backup scan yapmasın.

## Kontroller

- dashboard_bundle_includes_bot_scan: `evet`
- dashboard_bundle_uses_lightweight_rules: `evet`
- dashboard_cached_scan_has_filter_counts: `evet`
- dashboard_cached_scan_has_time_aliases: `evet`
- api_applies_bundle_bot_scan: `evet`
- api_heavy_sync_no_market_fetch: `evet`
- api_heavy_sync_keeps_last_scan_fetch: `evet`
- coinfilter_has_scan_normalizer: `evet`
- coinfilter_page_uses_normalized_scan: `evet`
- coinfilter_has_cached_scan_robust: `evet`
- coinfilter_row_counts_direct_keyed: `evet`
- coinfilter_test_scan_manual_only: `evet`
- dashboard_network_passed_true_only: `evet`
- dashboard_page_uses_normalized_scan: `evet`
- rule_store_status_default_no_deep_backup_scan: `evet`
- runtime_backup_rglob_guarded_by_deep: `evet`

## Blocker

Blocker yok.
