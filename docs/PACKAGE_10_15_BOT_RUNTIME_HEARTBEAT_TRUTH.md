# Paket 10.15 Bot Runtime Heartbeat Truth

## 1. Paket amaci

Paket 10.15, persistent `bot_running=true` bayraginin kullaniciya yanlis guven vermesini engeller.

Bot status artik su ayrimi yapar:

- `requested_running`
- `loop_alive`
- efektif `bot_running`
- `engine_status=running|stale|failed|stopped`
- tick/scan yaslari
- `primary_runtime_problem`

## 2. Heartbeat freshness

Default esikler:

- Tick stale threshold: `180` saniye
- Scan stale threshold: `300` saniye

Settings icinde `bot.tick_stale_threshold_seconds` veya `bot.scan_stale_threshold_seconds` verilirse kullanilir; default sabit kalir.

## 3. Runtime task registry

Yeni runtime registry alanlari:

- `bot_task_running`
- `bot_task_started_at`
- `bot_task_last_heartbeat_at`
- `bot_task_exception`

Scheduler thread start/heartbeat/exception durumunu registry'ye yazar.

## 4. Bot status truth

`GET /api/bot/status` artik persistent store bayragi yerine runtime truth hesaplar.

Stale durumda beklenen:

```json
{
  "requested_running": true,
  "loop_alive": false,
  "bot_running": false,
  "engine_status": "stale",
  "runtime_health_status": "degraded",
  "primary_runtime_problem": "bot_loop_not_alive"
}
```

Tick veya scan stale ise kullaniciya sadece `bot_running=true` guven sinyali verilmez.

## 5. Startup restore

Backend startup sirasinda `requested_running=true` olan paper/shadow botlar restore edilir.

Guvenlik kosullari:

- Real trading lock korunur.
- Mode paper/shadow olarak kalir.
- `emergency_lock` varsa restore edilmez.
- Emergency lock varsa `requested_running=false`, `bot_running=false`, `engine_status=stopped` yazilir.

## 6. Start / stop davranisi

`POST /api/bot/start`:

- `requested_running=true` yazar.
- Scheduler task alive degilse `ok=false`, `started=false`, `reason=bot_loop_task_failed_to_start` doner.
- Task alive olsa bile tick/scan henuz fresh degilse status truth bunu stale olarak gosterir.

`POST /api/bot/stop`:

- `requested_running=false`
- `bot_running=false`
- `engine_status=stopped`
- runtime user task state stopped

## 7. 8 saatlik rapor entegrasyonu

8 saatlik raporda `bot_decision` su alanlari tasir:

- `engine_status`
- `loop_alive`
- `requested_running`
- `last_tick_age_seconds`
- `last_scan_age_seconds`
- `primary_runtime_problem`

Bot stale ise `primary_no_trade_reason=bot_loop_stale` olur. CoinFilter/strategy sebepleri ikinci seviye bilgi olarak kalir.

## 8. Degisen dosyalar

- `backend/infrastructure/runtime/bot_runtime_registry.py`
- `backend/infrastructure/runtime/scheduler.py`
- `backend/services/bot_runtime_truth_service.py`
- `backend/services/bot_service.py`
- `backend/services/real_trade_safety_service.py`
- `backend/services/eight_hour_report_service.py`
- `backend/routes/bot_routes.py`
- `backend/main.py`
- `scripts/level1_40_30_bot_runtime_heartbeat_truth_audit.py`
- `docs/LEVEL1_40_30_BOT_RUNTIME_HEARTBEAT_TRUTH_AUDIT.json`
- `docs/LEVEL1_40_30_BOT_RUNTIME_HEARTBEAT_TRUTH_AUDIT.md`
- `docs/PACKAGE_10_15_BOT_RUNTIME_HEARTBEAT_TRUTH.md`
- `README.md`
- `todo.md`

## 9. Test sonuclari

- `py -X pycache_prefix=.pycache_paket10_15 -m py_compile backend\main.py backend\routes\bot_routes.py backend\services\bot_service.py backend\services\bot_runtime_truth_service.py backend\services\real_trade_safety_service.py backend\services\eight_hour_report_service.py backend\infrastructure\runtime\bot_runtime_registry.py backend\infrastructure\runtime\scheduler.py scripts\level1_40_30_bot_runtime_heartbeat_truth_audit.py`: pass
- `py -c "import sys; sys.path.insert(0, 'backend'); import main; print('backend import ok')"`: pass
- `py scripts\level1_40_30_bot_runtime_heartbeat_truth_audit.py`: pass, `status=ok`, `bot_status_has_requested_running=true`, `bot_status_has_loop_alive=true`, `bot_task_registry_present=true`, `bot_start_verifies_task_alive=true`, `previous_40_20_to_40_29_status_ok=true`
- `py scripts\level1_40_29_coinfilter_persistence_and_8h_report_audit.py`: pass, `status=ok`
- `py scripts\level1_40_28_runtime_health_paperlab_user_resolution_audit.py`: pass, `status=ok`
- `py scripts\level1_40_09_missing_endpoint_report.py`: pass, `missing_path_count=0`, `method_mismatch_count=0`, `true_blocker_count=0`, `parser_gap_or_false_positive_count=0`
- `py scripts\level1_40_08_api_contract_diff.py --strict`: pass, `status=ok`, `matched_call_count=94`, `missing_path_count=0`, `method_mismatch_count=0`
- `py -c "... build_bot_runtime_truth stale sample ..."`: pass, `requested_running=True`, `loop_alive=False`, `bot_running=False`, `engine_status=stale`, `primary_runtime_problem=bot_loop_not_alive`

## 10. Canli kabul testi

1. Backend restart edilir.
2. `/api/bot/status` kontrol edilir.
3. `requested_running=true` ise loop restore edilmelidir.
4. 3 dakika icinde `last_tick` ve `last_scan` guncellenmelidir.
5. Loop calismiyorsa response `engine_status=stale`, `loop_alive=false`, `primary_runtime_problem=bot_loop_not_alive` gostermelidir.
6. Kullaniciya bot calisiyor gibi yanlis bilgi verilmemelidir.

## 11. Paket 11'e gecis karari

Paket 11'e sadece 40.20-40.30 zinciri `ok` olduktan ve canli `/api/bot/status` restart/stale davranisi dogrulandiktan sonra gecilebilir.
