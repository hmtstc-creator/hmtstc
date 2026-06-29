# Level1 40.36.5 Rev3 Start Stop Runtime Contract Audit

## Ozet

- Durum: `ok`
- Start runtime contract: `evet`
- Stop runtime contract: `evet`
- Background worker default kapali: `evet`
- Read path worker baslatmiyor: `evet`

## Kontroller

- auto_scan_on_bot_start_default_false: `evet`
- auto_scan_on_status_read_default_false: `evet`
- auto_scan_on_dashboard_read_default_false: `evet`
- background_scan_worker_default_false: `evet`
- start_path_has_no_heavy_work: `evet`
- status_path_has_no_worker_start: `evet`
- dashboard_bundle_has_no_worker_start: `evet`
- start_runtime_contract_ok: `evet`
- start_idempotent: `evet`
- stop_runtime_contract_ok: `evet`
- status_stale_cleanup_only: `evet`
- worker_start_feature_guarded: `evet`
- main_background_loop_disabled: `evet`
- runtime_truth_heartbeat_mode_present: `evet`
- frontend_transient_status_nonfatal: `evet`
- frontend_pending_guard_present: `evet`
- dashboard_pending_buttons_disabled: `evet`
- prior_rev2_and_hard_cancel_ok: `evet`

## Call Graph

- `bot_start`: COMMAND_START heartbeat-only
- `bot_stop`: COMMAND_STOP cancel-and-clear
- `bot_status`: READ_ONLY plus stale cleanup
- `dashboard_bundle`: READ_ONLY
- `bot_tick`: MANUAL_SCAN
- `scan_debug_and_test_scan`: MANUAL_SCAN
- `main_bot_loop`: LEGACY_AUTO_SCAN disabled by feature flag
- `start_scan_worker`: SCHEDULED_SCAN disabled by feature flag

## Tetik Noktalari

- `scan_market`: backend\routes\bot_routes.py:331, backend\routes\bot_routes.py:449, backend\services\bot_service.py:347
- `start_scan_worker`: backend\main.py:347
- `active_scan_worker_true`: backend\infrastructure\runtime\bot_scan_worker.py:77, backend\infrastructure\runtime\bot_scan_worker.py:236
- `deep_analysis_true`: backend\routes\bot_routes.py:331, backend\services\bot_service.py:347
- `create_task`: yok
- `thread_or_process`: backend\infrastructure\runtime\bot_loop_control.py:193, backend\infrastructure\runtime\bot_scan_worker.py:253, backend\infrastructure\runtime\bot_scan_worker.py:259

## Blocker Listesi

Blocker yok.

## Sonuc

Heartbeat-only start/stop runtime contract ve zero-background-worker kapisi temiz.
