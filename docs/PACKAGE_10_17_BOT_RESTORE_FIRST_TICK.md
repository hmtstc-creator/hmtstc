# Paket 10.17 Bot Restore First Tick

## 1. Paket amaci

Paket 10.17, bot restore basarisinin sadece scheduler thread alive gorunmesine baglanmasini engeller.

Restore basarisi icin artik ilk gercek bot tick/scan kaniti gerekir:

- `last_runtime_restore_first_tick_ok_at` dolu olmali
- veya `last_tick` restore baslangicindan sonra guncellenmeli
- ve `last_scan.time` restore baslangicindan sonra guncellenmeli

Thread alive tek basina `loop_alive=true` yapmaz.

## 2. Restore result contract

`last_runtime_restore_result` artik su alanlari tasir:

```json
{
  "started": true,
  "already_running": false,
  "thread_alive": true,
  "first_tick_ok": false,
  "loop_alive": false,
  "reason": "restore_no_first_tick",
  "restore_started_at": "...",
  "checked_at": "..."
}
```

## 3. Non-blocking watchdog

Startup hizli kalir. `ensure_bot_loop_running` scheduler'i baslatir, sonucu yazar ve restore first tick watchdog thread'i baslatir.

Watchdog:

- Ilk tick/scan gelirse `engine_status=running`, `bot_running=true`
- 180 saniye icinde gelmezse `engine_status=failed`, `primary_runtime_problem=restore_no_first_tick`, `bot_running=false`

## 4. Status davranisi

Thread alive ama ilk tick yoksa:

```json
{
  "requested_running": true,
  "thread_alive": true,
  "loop_alive": false,
  "bot_running": false,
  "engine_status": "restoring",
  "primary_runtime_problem": "waiting_first_tick"
}
```

180 saniye sonra:

```json
{
  "engine_status": "failed",
  "primary_runtime_problem": "restore_no_first_tick"
}
```

## 5. Bot loop diagnostics

Bot loop her kullanici icin runtime log yazar:

- `BOT_LOOP_USER_CHECK`
- `BOT_LOOP_TICK_START`
- `BOT_LOOP_TICK_OK`
- `BOT_LOOP_TICK_FAILED`

`run_bot_tick` exception veya uzun calisma durumunda:

- `engine_status=failed`
- `primary_runtime_problem=run_bot_tick_exception` veya `run_bot_tick_timeout`
- `last_runtime_error`

## 6. 8 saatlik rapor entegrasyonu

Restore first tick fail olursa:

```json
{
  "primary_no_trade_reason": "bot_restore_failed",
  "primary_runtime_problem": "restore_no_first_tick"
}
```

## 7. Degisen dosyalar

- `backend/infrastructure/runtime/bot_loop_control.py`
- `backend/services/bot_runtime_truth_service.py`
- `backend/services/eight_hour_report_service.py`
- `backend/main.py`
- `scripts/level1_40_31_bot_restore_real_loop_audit.py`
- `scripts/level1_40_32_bot_restore_first_tick_audit.py`
- `docs/LEVEL1_40_32_BOT_RESTORE_FIRST_TICK_AUDIT.json`
- `docs/LEVEL1_40_32_BOT_RESTORE_FIRST_TICK_AUDIT.md`
- `docs/PACKAGE_10_17_BOT_RESTORE_FIRST_TICK.md`
- `README.md`
- `todo.md`

## 8. Test sonuclari

- `py -X pycache_prefix=.pycache_paket10_17 -m py_compile backend\main.py backend\infrastructure\runtime\bot_loop_control.py backend\services\bot_runtime_truth_service.py backend\services\eight_hour_report_service.py scripts\level1_40_31_bot_restore_real_loop_audit.py scripts\level1_40_32_bot_restore_first_tick_audit.py`: pass
- `py -c "import sys; sys.path.insert(0, 'backend'); import main; print('backend import ok')"`: pass
- `py scripts\level1_40_32_bot_restore_first_tick_audit.py`: pass, `status=ok`, `ensure_bot_loop_running_does_not_accept_thread_only=true`, `restore_first_tick_required=true`, `restore_monitor_or_watchdog_present=true`, `previous_40_20_to_40_31_status_ok=true`
- `py scripts\level1_40_31_bot_restore_real_loop_audit.py`: pass, `status=ok`
- `py scripts\level1_40_30_bot_runtime_heartbeat_truth_audit.py`: pass, `status=ok`
- `py scripts\level1_40_29_coinfilter_persistence_and_8h_report_audit.py`: pass, `status=ok`
- `py scripts\level1_40_09_missing_endpoint_report.py`: pass, `missing_path_count=0`, `method_mismatch_count=0`, `true_blocker_count=0`, `parser_gap_or_false_positive_count=0`
- `py scripts\level1_40_08_api_contract_diff.py --strict`: pass, `status=ok`, `matched_call_count=94`, `missing_path_count=0`, `method_mismatch_count=0`
- `py -c "... waiting first tick sample ..."`: pass, `engine_status=restoring`, `primary_runtime_problem=waiting_first_tick`, `loop_alive=False`, `bot_running=False`
- `py -c "... restore timeout sample ..."`: pass, `engine_status=failed`, `primary_runtime_problem=restore_no_first_tick`, `loop_alive=False`, `bot_running=False`

## 9. Canli kabul testi

Deploy ve restart sonrasi:

1. `last_runtime_restore_result.thread_alive=true` tek basina basari sayilmaz.
2. `last_runtime_restore_first_tick_ok_at` dolmadan `loop_alive=true` donmez.
3. 180 saniye icinde tick gelirse `engine_status=running`, `loop_alive=true`, `bot_running=true`.
4. Tick gelmezse `engine_status=failed`, `loop_alive=false`, `bot_running=false`, `primary_runtime_problem=restore_no_first_tick`.
5. Shadow store loglarinda `BOT_LOOP_USER_CHECK`, `BOT_LOOP_TICK_START`, `BOT_LOOP_TICK_OK` veya `BOT_LOOP_TICK_FAILED` gorunur.

## 10. Paket 11'e gecis karari

Paket 11'e sadece 40.20-40.32 zinciri `ok` olduktan ve canli restart sonrasi first tick kabul testi gectikten sonra gecilebilir.
