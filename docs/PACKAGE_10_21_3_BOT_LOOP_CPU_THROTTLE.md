# Paket 10.21.3 Bot Loop CPU Throttle

## Amac

Bot kapaliyken backend background scheduler'in scan, tick veya restore isi baslatmasini engeller. Bot acikken tick tekrarlarini zaman kapisi ve hata backoff'u ile sinirlar.

## Startup ve stopped davranisi

- Startup restore sadece `requested_running=true` kullanicilari ele alir.
- Stopped kullanici icin `ensure_bot_loop_running`, scan, tick, log veya store write calismaz.
- Startup'ta istekli kullanici yoksa runtime scheduler baslatilmaz.
- Calisan scheduler'da istekli kullanici kalmazsa loop temiz sekilde kapanir.
- Scheduler temiz cikistan sonra yeni bot start istegiyle tekrar baslatilabilir.

## Tick throttle

- Minimum tick araligi `30` saniyedir.
- `tick_in_progress=true` iken ikinci tick baslamaz.
- Hata veya basarisiz tick sonrasi backoff en az `60` saniyedir.
- Runtime state `last_tick_started_at`, `last_tick_finished_at` ve `next_tick_not_before` alanlarini tutar.
- Stop ve emergency stop `tick_in_progress=false`, `next_tick_not_before=null` yazar.

## Analiz ve API izolasyonu

- Normal bot loop deep teknik analiz limiti en fazla `8` semboldur.
- CoinFilter lightweight test scan davranisi degismedi.
- Dashboard bundle, bot status, settings, rules, positions, API connection ve Binance market read endpointleri bot tick veya scan scheduler baslatmaz.

## Degisen dosyalar

- `backend/main.py`
- `backend/core/config.py`
- `backend/core/storage.py`
- `backend/services/bot_service.py`
- `backend/services/analysis_service.py`
- `backend/infrastructure/runtime/scheduler.py`
- `backend/infrastructure/runtime/bot_loop_control.py`
- `scripts/level1_40_36_1_bot_loop_none_numeric_hotfix_audit.py`
- `scripts/level1_40_36_3_bot_loop_cpu_throttle_audit.py`
- `docs/LEVEL1_40_36_3_BOT_LOOP_CPU_THROTTLE_AUDIT.json`
- `docs/LEVEL1_40_36_3_BOT_LOOP_CPU_THROTTLE_AUDIT.md`
- `docs/PACKAGE_10_21_3_BOT_LOOP_CPU_THROTTLE.md`
- `README.md`
- `todo.md`

## Test sonuclari

- `py -m py_compile backend\main.py backend\core\config.py backend\core\storage.py backend\services\bot_service.py backend\services\analysis_service.py backend\infrastructure\runtime\scheduler.py backend\infrastructure\runtime\bot_loop_control.py scripts\level1_40_36_1_bot_loop_none_numeric_hotfix_audit.py scripts\level1_40_36_3_bot_loop_cpu_throttle_audit.py`: pass
- `py scripts\level1_40_36_3_bot_loop_cpu_throttle_audit.py`: pass, `status=ok`, stopped runtime probe background work count `0`, deep cap `8`
- `py scripts\level1_40_36_2_status_field_sync_hotfix_audit.py`: pass, `status=ok`
- `py scripts\level1_40_36_1_bot_loop_none_numeric_hotfix_audit.py`: pass, `status=ok`
- `py scripts\level1_40_36_bot_start_and_coinfilter_save_stability_audit.py`: pass, `status=ok`
- `py scripts\level1_40_35_last_scan_contract_preservation_audit.py`: pass, `status=ok`
- `py scripts\level1_40_34_coinfilter_test_scan_timeout_audit.py`: pass, `status=ok`
- `py scripts\level1_40_09_missing_endpoint_report.py`: pass, blocker yok
- `py scripts\level1_40_08_api_contract_diff.py --strict`: pass, `matched_call_count=94`, missing/mismatch yok
- Backend import: pass, `backend import ok`
- Scheduler clean-exit/restart runtime probe: pass
- `git diff --check`: pass

## Canli kabul

Bot kapaliyken `requested_running=false`, `bot_running=false`, `engine_status=stopped` kalmali ve uvicorn CPU surekli yuksek olmamalidir.

Bot acikken iki dakika gozlemde CPU surekli yuzde 100 kalmamali; Dashboard, rules, wallet ve scan cevaplari erisilebilir kalmalidir.

Canli CPU ve endpoint gecikme kabulü deploy sonrasi VPS uzerinde yapilmalidir.
