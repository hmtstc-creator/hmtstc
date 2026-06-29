# Level1 40.36.3 Bot Loop CPU Throttle Audit

## Ozet

- Durum: `ok`
- Stopped scheduler skip: `evet`
- Tick in-progress guard: `evet`
- Error backoff: `evet`
- Deep analysis cap: `8`
- API isolation: `evet`

## Kontroller

- stopped_restore_skips_ensure_bot_loop_running: `evet`
- stopped_scheduler_skips_scan_and_tick: `evet`
- stopped_runtime_probe_has_zero_background_work: `evet`
- scheduler_stops_when_no_requested_users: `evet`
- requested_running_default_true_absent: `evet`
- ensure_loop_rejects_stopped_user: `evet`
- tick_in_progress_guard_present: `evet`
- min_tick_interval_seconds_at_least_30: `evet`
- error_backoff_at_least_60: `evet`
- deep_analysis_cap_at_most_8: `evet`
- api_read_endpoints_do_not_trigger_scan: `evet`
- stop_clears_loop_throttle_state: `evet`
- inflight_tick_respects_persisted_stop: `evet`
- scheduler_can_restart_after_clean_exit: `evet`
- scheduler_start_race_guard_present: `evet`
- prior_40_36_audits_ok: `evet`

## Blocker Listesi

Blocker yok.

## Sonuc

Bot loop CPU throttle kalite kapisi temiz.
