# Paket 10.21.1 Bot Loop None Numeric Hotfix

## Amac

Canli bot loop icinde None veya gecersiz market/indicator degerlerinin sayisal karsilastirmaya girmesini engeller.

## Davranis

- Kline hucreleri finite float olarak normalize edilir.
- None, NaN, Infinity veya bozuk indicator sonucu coin-level reject olur.
- Reject nedenleri `invalid_numeric_indicator` veya `missing_numeric_indicator` olarak raporlanir.
- Scan row numeric alanlari daima sayisal deger tasir.
- Bot candidate price ve position size guvenli float kullanir.
- Paper Lab stability, execution quality ve drawdown karsilastirmalari safe float kullanir.
- Pozisyon TP/SL kontrolu gecersiz current price degerini karsilastirmadan atlar.
- Normal bot tick deep teknik analiz aday sayisi en fazla 12'dir.
- User-level bot loop hatasi tum scheduler task'ini oldurmez.
- Traceback, exception tipi ve mesaj runtime state/log icinde saklanir.
- Teknik hata `requested_running=true` kullanici istegini degistirmez.
- Runtime status generik hata yerine persisted gercek problem sebebini doner.

## Degisen dosyalar

- `backend/services/analysis_service.py`
- `backend/services/bot_service.py`
- `backend/services/bot_runtime_truth_service.py`
- `backend/services/paper_lab_service.py`
- `backend/services/position_service.py`
- `backend/main.py`
- `scripts/level1_40_36_1_bot_loop_none_numeric_hotfix_audit.py`
- `docs/LEVEL1_40_36_1_BOT_LOOP_NONE_NUMERIC_HOTFIX_AUDIT.json`
- `docs/LEVEL1_40_36_1_BOT_LOOP_NONE_NUMERIC_HOTFIX_AUDIT.md`
- `docs/PACKAGE_10_21_1_BOT_LOOP_NONE_NUMERIC_HOTFIX.md`
- `README.md`
- `todo.md`

## Test sonuclari

- `py -X pycache_prefix=.pycache_paket10_21_1 -m py_compile backend\main.py backend\services\analysis_service.py backend\services\bot_service.py backend\services\bot_runtime_truth_service.py backend\services\paper_lab_service.py backend\services\position_service.py scripts\level1_40_36_1_bot_loop_none_numeric_hotfix_audit.py`: pass
- `py -c "import sys; sys.path.insert(0, 'backend'); import main; print('backend import ok')"`: pass, `backend import ok`
- `py scripts\level1_40_36_1_bot_loop_none_numeric_hotfix_audit.py`: pass, `status=ok`, `null_kline_rejected_without_crash=true`, `null_indicator_rejected_without_crash=true`, `bot_loop_traceback_logging_present=true`, `prior_40_36_status=ok`
- None kline runtime probe: pass, coin `invalid_numeric_indicator` ile reject edildi
- None RSI runtime probe: pass, coin `invalid_numeric_indicator` ile reject edildi
- None market ticker runtime probe: pass, scan `status=ok`, candidate `0`, row `REJECT`, numeric contract finite
- Paper Lab score/drawdown ve position current-price None guard kontrolleri: pass
- `py scripts\level1_40_36_bot_start_and_coinfilter_save_stability_audit.py`: pass, `status=ok`
- `py scripts\level1_40_35_last_scan_contract_preservation_audit.py`: pass, `status=ok`
- `py scripts\level1_40_34_coinfilter_test_scan_timeout_audit.py`: pass, `status=ok`
- `py scripts\level1_40_32_bot_restore_first_tick_audit.py`: pass, `status=ok`
- `py scripts\level1_40_31_bot_restore_real_loop_audit.py`: pass, `status=ok`
- `py scripts\level1_40_30_bot_runtime_heartbeat_truth_audit.py`: pass, `status=ok`
- `py scripts\level1_40_09_missing_endpoint_report.py`: pass, blocker yok
- `py scripts\level1_40_08_api_contract_diff.py --strict`: pass, missing/mismatch yok

Canli scheduler thread, ilk tick suresi ve log gozlemi deploy sonrasi kabul edilmelidir.

## Canli kabul

- Bot Acik sonrasi `requested_running=true` kalir.
- Thread ve ilk tick basariliysa `loop_alive=true`, `bot_running=true` olur.
- Ilk tick beklenirken `engine_status=starting/restoring` gorunebilir.
- Loglarda `NoneType` ile float karsilastirma hatasi gorulmez.
- Bozuk coin verisi loop crash yerine reject olur.
- Coin tarama deep analiz cap nedeniyle 5-6 dakika surmez.
