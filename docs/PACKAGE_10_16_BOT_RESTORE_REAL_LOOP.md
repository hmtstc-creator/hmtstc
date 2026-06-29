# Paket 10.16 Bot Restore Real Loop

## 1. Paket amaci

Paket 10.16, backend restart sonrasi `requested_running=true` olan botun sadece store bayragi ile restore edilmis sayilmasini engeller.

Ana karar:

- Restore fonksiyonu heartbeat yazmaz.
- Heartbeat sadece gercek bot loop/tick iteration icinden yazilir.
- Restore ve manuel start ayni `ensure_bot_loop_running` helper'ini kullanir.
- Canli task dogrulamasi registry flag yerine gercek thread referansi ve taze heartbeat ile yapilir.

## 2. Sahte heartbeat kaldirildi

`mark_bot_task_heartbeat()` artik `bot_task_running=true` yazmaz.

Task alive kontrolu sunlara bakar:

- Gercek thread referansi var mi?
- Thread `is_alive()` mi?
- Global heartbeat threshold icinde mi?
- Kullanici task exception kaydi var mi?

## 3. Ortak loop starter

Yeni helper:

```python
ensure_bot_loop_running(username: str, mode: str) -> dict
```

Hem startup restore hem de `POST /api/bot/start` ayni helper'i kullanir.

## 4. Restore log zinciri

Startup restore su loglari yazar:

- `BOT_RESTORE_CHECK user=... requested_running=true/false`
- `BOT_RESTORE_START user=... mode=...`
- `BOT_RESTORE_TASK_STARTED user=...`
- `BOT_RESTORE_FIRST_TICK_OK user=...`
- `BOT_RESTORE_FAILED user=... reason=...`

## 5. Ilk tick/scan guard

Restore sonrasi 180 saniye icinde tick veya scan fresh degilse runtime truth:

```json
{
  "engine_status": "failed",
  "primary_runtime_problem": "restore_no_tick_after_start"
}
```

## 6. 8 saatlik rapor entegrasyonu

Restore fail ise 8 saatlik raporda:

```json
{
  "primary_no_trade_reason": "bot_restore_failed",
  "primary_runtime_problem": "restore_no_tick_after_start"
}
```

## 7. Degisen dosyalar

- `backend/infrastructure/runtime/bot_runtime_registry.py`
- `backend/infrastructure/runtime/scheduler.py`
- `backend/infrastructure/runtime/bot_loop_control.py`
- `backend/main.py`
- `backend/routes/bot_routes.py`
- `backend/services/bot_runtime_truth_service.py`
- `backend/services/eight_hour_report_service.py`
- `scripts/level1_40_30_bot_runtime_heartbeat_truth_audit.py`
- `scripts/level1_40_31_bot_restore_real_loop_audit.py`
- `docs/LEVEL1_40_31_BOT_RESTORE_REAL_LOOP_AUDIT.json`
- `docs/LEVEL1_40_31_BOT_RESTORE_REAL_LOOP_AUDIT.md`
- `docs/PACKAGE_10_16_BOT_RESTORE_REAL_LOOP.md`
- `README.md`
- `todo.md`

## 8. Test sonuclari

- `py -X pycache_prefix=.pycache_paket10_16 -m py_compile backend\main.py backend\routes\bot_routes.py backend\services\bot_runtime_truth_service.py backend\services\eight_hour_report_service.py backend\infrastructure\runtime\bot_runtime_registry.py backend\infrastructure\runtime\scheduler.py backend\infrastructure\runtime\bot_loop_control.py scripts\level1_40_30_bot_runtime_heartbeat_truth_audit.py scripts\level1_40_31_bot_restore_real_loop_audit.py`: pass
- `py -c "import sys; sys.path.insert(0, 'backend'); import main; print('backend import ok')"`: pass
- `py scripts\level1_40_31_bot_restore_real_loop_audit.py`: pass, `status=ok`, `restore_does_not_fake_heartbeat=true`, `ensure_bot_loop_running_present=true`, `start_and_restore_share_loop_starter=true`, `is_bot_task_alive_checks_real_task_reference=true`, `previous_40_20_to_40_30_status_ok=true`
- `py scripts\level1_40_30_bot_runtime_heartbeat_truth_audit.py`: pass, `status=ok`
- `py scripts\level1_40_29_coinfilter_persistence_and_8h_report_audit.py`: pass, `status=ok`
- `py scripts\level1_40_09_missing_endpoint_report.py`: pass, `missing_path_count=0`, `method_mismatch_count=0`, `true_blocker_count=0`, `parser_gap_or_false_positive_count=0`
- `py scripts\level1_40_08_api_contract_diff.py --strict`: pass, `status=ok`, `matched_call_count=94`, `missing_path_count=0`, `method_mismatch_count=0`
- `py -c "... restore first tick guard sample ..."`: pass, `engine_status=failed`, `primary_runtime_problem=restore_no_tick_after_start`, `bot_running=False`

## 9. Canli kabul testi

Deploy sonrasi:

```bash
sudo journalctl -u hmtstc-backend.service --since "5 minutes ago" --no-pager | grep -Ei "BOT_RESTORE|bot loop|heartbeat|tick|scan|failed|exception"
```

Beklenen:

```text
BOT_RESTORE_CHECK user=ahmet requested_running=true
BOT_RESTORE_START user=ahmet
BOT_RESTORE_TASK_STARTED user=ahmet
```

3 dakika icinde `/api/bot/status`:

```json
{
  "requested_running": true,
  "loop_alive": true,
  "bot_running": true,
  "engine_status": "running"
}
```

ve `last_tick_age_seconds < 180`, `last_scan_age_seconds < 300` olmalidir.

Fail halinde:

```json
{
  "requested_running": true,
  "loop_alive": false,
  "bot_running": false,
  "engine_status": "failed",
  "primary_runtime_problem": "restore_no_tick_after_start"
}
```

## 10. Paket 11'e gecis karari

Paket 11'e sadece 40.20-40.31 zinciri `ok` olduktan ve canli restart restore log/tick/scan kabul testi gecildikten sonra gecilebilir.
