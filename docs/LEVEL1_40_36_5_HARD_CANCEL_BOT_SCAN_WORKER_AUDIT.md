# Level1 40.36.5 Hard Cancel Bot Scan Worker Audit

## Ozet

- Durum: `ok`
- Lightweight first tick: `evet`
- Separate scan worker: `evet`
- Generation guard: `evet`
- Timeout cancel: `evet`
- CoinFilter cached view: `evet`

## Kontroller

- first_tick_lightweight_mode_present: `evet`
- first_tick_does_not_use_deep_analysis: `evet`
- start_endpoint_is_non_blocking: `evet`
- scan_worker_state_fields_present: `evet`
- scan_worker_runs_in_separate_thread: `evet`
- scan_worker_generation_guard_present: `evet`
- timeout_cancels_scan_worker: `evet`
- stop_and_emergency_cancel_worker: `evet`
- failed_state_cpu_guard_present: `evet`
- scan_loop_cancel_deadline_guard_present: `evet`
- deep_analysis_cancel_deadline_guard_present: `evet`
- strategy_filter_cancel_guard_present: `evet`
- deep_network_timeout_uses_remaining_deadline: `evet`
- public_market_timeout_at_most_three_seconds: `evet`
- last_scan_endpoint_is_cached_read: `evet`
- dashboard_bundle_does_not_start_scan: `evet`
- frontend_start_success_message_present: `evet`
- coinfilter_cached_empty_message_present: `evet`
- scheduler_uses_light_first_tick_and_background_worker: `evet`
- prior_40_36_3_and_40_36_4_ok: `evet`

## Blocker Listesi

Blocker yok.

## Sonuc

Lightweight first tick, generation guard ve scan worker cancel kalite kapisi temiz.
