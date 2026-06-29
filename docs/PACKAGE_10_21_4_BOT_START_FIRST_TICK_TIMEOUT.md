# Paket 10.21.4 Bot Start First Tick Timeout

## Amac

Bot start sonrasi agir first tick'in HTTP start istegini, scheduler state'ini ve backend CPU'yu uzun sure kilitlemesini engeller.

## Non-blocking start

- `/api/bot/start` first tick veya deep analysis sonucunu beklemez.
- Scheduler thread baslangici en fazla `0.25` saniye kontrol edilir.
- Start sonucu `starting/restoring` olarak hemen doner.
- Frontend 200 cevabini generic API hatasi saymaz ve first tick sonucunu ayri status istegiyle izler.

## First tick ve scan timeout

- First tick watchdog suresi `25` saniyedir.
- Normal bot scan toplam deadline'i en fazla `20` saniyedir.
- Deep teknik analiz deadline'i en fazla `15` saniyedir.
- Binance public request timeout'u kalan deadline ile sinirlanir.
- Timeout veya exception durumunda `run_bot_tick_guarded` finally blogu `tick_in_progress=false` yazar.

## Guvenli failed state

First tick zaman asiminda:

```json
{
  "requested_running": false,
  "bot_running": false,
  "engine_status": "failed",
  "primary_runtime_problem": "first_tick_timeout",
  "tick_in_progress": false,
  "next_tick_not_before": null
}
```

Watchdog stop state'ini store'a yazar; devam eden cooperative scan dondugunde persisted stop guard eski local state'in bunu geri almasini engeller.

## Cached scan gorunumu

- `/api/bot/last-scan` yalnizca runtime store'daki son scan'i doner.
- `/api/dashboard/bundle` yeni scan baslatmaz ve son scan zamanini korur.
- `/api/binance/market?strict=false` public read timeout'u 3 saniye ile sinirlidir.
- Dashboard yeni first tick beklerken mevcut scan bilgisini gostermeye devam eder.

## Degisen dosyalar

- `backend/main.py`
- `backend/services/market_service.py`
- `backend/services/analysis_service.py`
- `backend/services/bot_service.py`
- `backend/services/bot_runtime_truth_service.py`
- `backend/infrastructure/runtime/bot_loop_control.py`
- `backend/routes/bot_routes.py`
- `frontend/js/app/bot.js`
- `scripts/level1_40_36_bot_start_and_coinfilter_save_stability_audit.py`
- `scripts/level1_40_36_1_bot_loop_none_numeric_hotfix_audit.py`
- `scripts/level1_40_36_3_bot_loop_cpu_throttle_audit.py`
- `scripts/level1_40_36_4_bot_start_first_tick_timeout_audit.py`
- `docs/LEVEL1_40_36_4_BOT_START_FIRST_TICK_TIMEOUT_AUDIT.json`
- `docs/LEVEL1_40_36_4_BOT_START_FIRST_TICK_TIMEOUT_AUDIT.md`
- `docs/PACKAGE_10_21_4_BOT_START_FIRST_TICK_TIMEOUT.md`
- `README.md`
- `todo.md`

## Test sonuclari

- `py -m py_compile backend\main.py backend\services\market_service.py backend\services\analysis_service.py backend\services\bot_service.py backend\services\bot_runtime_truth_service.py backend\infrastructure\runtime\bot_loop_control.py backend\routes\bot_routes.py backend\routes\binance_routes.py scripts\level1_40_36_4_bot_start_first_tick_timeout_audit.py`: pass
- `py scripts\level1_40_36_4_bot_start_first_tick_timeout_audit.py`: pass, `status=ok`, finally unlock runtime probe `true`
- `py scripts\level1_40_36_3_bot_loop_cpu_throttle_audit.py`: pass, `status=ok`
- `py scripts\level1_40_36_2_status_field_sync_hotfix_audit.py`: pass, `status=ok`
- `py scripts\level1_40_36_1_bot_loop_none_numeric_hotfix_audit.py`: pass, `status=ok`
- `py scripts\level1_40_36_bot_start_and_coinfilter_save_stability_audit.py`: pass, `status=ok`
- `py scripts\level1_40_35_last_scan_contract_preservation_audit.py`: pass, `status=ok`
- `py scripts\level1_40_34_coinfilter_test_scan_timeout_audit.py`: pass, `status=ok`
- `py scripts\level1_40_09_missing_endpoint_report.py`: pass, blocker yok
- `py scripts\level1_40_08_api_contract_diff.py --strict`: pass, `matched_call_count=94`, missing/mismatch yok
- Backend import: pass, `backend import ok`
- Frontend `bot.js`, `api.js`, `dashboard.js`, `state.js` Node VM syntax compile: pass
- `git diff --check`: pass

## Canli kabul

- Bot kapaliyken CPU dusuk ve `tick_in_progress=false` kalir.
- Start API 200 cevabini hizli doner.
- First tick tamamlanir veya 25 saniyede `first_tick_timeout` ile guvenli failed state olusur.
- Dashboard mevcut last scan bilgisini first tick beklerken kaybetmez.
- CPU surekli yuzde 100 ve RAM 1 GB seviyesinde kalmaz.

Canli CPU, RAM ve ilk tick kabulü deploy sonrasi VPS uzerinde yapilmalidir.
