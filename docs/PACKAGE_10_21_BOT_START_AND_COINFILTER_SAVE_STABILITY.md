# Paket 10.21 Bot Start and CoinFilter Save Stability

## 1. Paket amaci

Paket 10.21, CoinFilter ayar kaydetme sirasindaki timeout/AbortError ayrimini ve bot start sirasindaki kullanici istegi/gercek loop durumu ayrimini duzeltir.

Paket 10.22 bu pakette baslatilmadi. Execution Mode Control, Paket 10.21 canli kabulunden sonra ele alinmalidir.

## 2. CoinFilter save stability

- POST settings request'i bagimsiz mutation olarak calisir.
- Save devam ederken ikinci save engellenir.
- Timeout abort, ham `AbortError` yerine `timeout` olarak siniflandirilir.
- Save sonrasi backend settings tekrar okunur.
- Payload, response, store echo ve refresh echo karsilastirilir.
- UI `Kaydediliyor...`, `Başarıyla kaydedildi` ve `Kaydetme başarısız: <sebep>` durumlarini gosterir.
- Hata halinde yerel draft korunur.

## 3. Scan settings proof

`scan_diagnostics.coin_filter_settings_used` su ayarlari raporlar:

- Hacim ve trade limitleri
- Volatilite interval/candle ayarlari
- 15m, 1h ve 4h RSI limitleri
- Volume growth multiplier
- Normalize excluded symbols
- Configured deep analysis limit

CoinFilter test scan'de deep analiz yine kapali kalir.

## 4. Bot start truth

Start istegi:

- `requested_running=true`
- Ilk tick oncesi `bot_running=false`
- `engine_status=starting/restoring`
- Onceki restore/first-tick kaniti temizlenir ve yeni start zamani yazilir.
- Gercek thread baslatilir ve first-tick watchdog calisir.
- Thread baslamazsa `engine_status=failed` olur fakat `requested_running=true` korunur.

Status response `thread_alive`, `loop_alive`, `bot_running`, `engine_status` ve `primary_runtime_problem` alanlarini ayri doner.

Frontend start akisi `requested_running=true` ve `starting/restoring` durumunu hata saymaz; ilk tick bekleniyor olarak gosterir. Failed durumda kullanici istegi ile teknik problem ayri gorunur. Kullanici, failed/restoring durumda da stop istegi verebilir.

Kullanici stop istegi `stop_reason=user_requested_stop` ve `requested_running=false` yazar.

## 5. Diagnostics eventleri

- `BOT_START_REQUESTED`
- `BOT_START_TASK_STARTED`
- `BOT_START_FIRST_TICK_OK`
- `BOT_START_FAILED`
- `BOT_LOOP_USER_CHECK`
- `BOT_LOOP_TICK_START`
- `BOT_LOOP_TICK_OK`
- `BOT_LOOP_TICK_FAILED`
- `BOT_STOP_REQUESTED`

## 6. Yeni audit

- `scripts/level1_40_36_bot_start_and_coinfilter_save_stability_audit.py`
- `docs/LEVEL1_40_36_BOT_START_AND_COINFILTER_SAVE_STABILITY_AUDIT.json`
- `docs/LEVEL1_40_36_BOT_START_AND_COINFILTER_SAVE_STABILITY_AUDIT.md`

Audit, statik contract kontrollerine ek olarak CoinFilter settings snapshot ve bot start state runtime probe'lari calistirir.

## 7. Degisen dosyalar

- `frontend/js/pages/coinFilter.js`
- `frontend/js/app/api.js`
- `frontend/js/app/state.js`
- `frontend/js/app/bot.js`
- `frontend/js/pages/dashboard.js`
- `backend/routes/bot_routes.py`
- `backend/services/bot_service.py`
- `backend/services/bot_runtime_truth_service.py`
- `backend/infrastructure/runtime/bot_loop_control.py`
- `backend/services/analysis_service.py`
- `scripts/level1_40_36_bot_start_and_coinfilter_save_stability_audit.py`
- `docs/LEVEL1_40_36_BOT_START_AND_COINFILTER_SAVE_STABILITY_AUDIT.json`
- `docs/LEVEL1_40_36_BOT_START_AND_COINFILTER_SAVE_STABILITY_AUDIT.md`
- `docs/PACKAGE_10_21_BOT_START_AND_COINFILTER_SAVE_STABILITY.md`
- `README.md`
- `todo.md`

## 8. Test sonuclari

- `py -X pycache_prefix=.pycache_paket10_21 -m py_compile backend\services\analysis_service.py backend\services\bot_service.py backend\services\bot_runtime_truth_service.py backend\routes\bot_routes.py backend\infrastructure\runtime\bot_loop_control.py scripts\level1_40_36_bot_start_and_coinfilter_save_stability_audit.py`: pass
- `py -c "import sys; sys.path.insert(0, 'backend'); import main; print('backend import ok')"`: pass, `backend import ok`
- `py scripts\level1_40_36_bot_start_and_coinfilter_save_stability_audit.py`: pass, `status=ok`, `coinfilter_save_polling_abort_isolated=true`, `scan_diagnostics_settings_used_present=true`, `bot_start_requested_running_true=true`, `previous_40_20_to_40_35_status_ok=true`
- 40.36 CoinFilter settings runtime probe: pass; tum zorunlu alanlar korundu, `excluded_symbols=[BTCUSDT, XRPUSDT]`
- 40.36 bot start runtime probe: pass, `requested_running=true`, `bot_running=false`, `engine_status=starting`, `primary_runtime_problem=waiting_first_tick`
- `py scripts\level1_40_35_last_scan_contract_preservation_audit.py`: pass, `status=ok`
- `py scripts\level1_40_34_coinfilter_test_scan_timeout_audit.py`: pass, `status=ok`
- `py scripts\level1_40_33_coinfilter_final_pipeline_audit.py`: pass, `status=ok`
- `py scripts\level1_40_32_bot_restore_first_tick_audit.py`: pass, `status=ok`
- `py scripts\level1_40_31_bot_restore_real_loop_audit.py`: pass, `status=ok`
- `py scripts\level1_40_30_bot_runtime_heartbeat_truth_audit.py`: pass, `status=ok`
- `py scripts\level1_40_29_coinfilter_persistence_and_8h_report_audit.py`: pass, `status=ok`
- `py scripts\level1_40_09_missing_endpoint_report.py`: pass, `missing_path_count=0`, `method_mismatch_count=0`, `true_blocker_count=0`, `parser_gap_or_false_positive_count=0`
- `py scripts\level1_40_08_api_contract_diff.py --strict`: pass, `matched_call_count=94`, `missing_path_count=0`, `method_mismatch_count=0`
- Node REPL `vm.Script` parse: pass, `coinFilter.js`, `dashboard.js`, `api.js`, `state.js`, `bot.js`

CoinFilter save, Ctrl+F5 persistence, bot scheduler/thread ve first tick sonucu canli ortamda kabul edilmelidir. Paket 10.22 bu canli kabul tamamlanmadan baslatilmadi.

## 9. Canli kabul

CoinFilter:

1. Ayar degistirilir ve kaydedilir.
2. Basari durumu gorulur.
3. Ctrl+F5 sonrasi ayni ayar geri gelir.
4. Test scan ve last-scan ayni sayilari ve `coin_filter_settings_used` degerlerini doner.

Bot:

1. Dashboard'dan Bot Acik secilir.
2. `requested_running=true` kalir.
3. Thread ve ilk tick basariliysa `engine_status=running` olur.
4. Basarisizsa `requested_running=true`, `bot_running=false`, `engine_status=failed` ve problem sebebi gorulur.

## 10. Paket 10.22 karari

Paket 10.22 yalnizca CoinFilter save, test scan/last-scan esitligi ve bot start canli kabul adimlari gectikten sonra baslatilabilir.
