# Paket 10.21.5 Revize 2 First Tick Heartbeat

## Amac

Bot start sonrasi first tick'i tum piyasa ve analiz islerinden ayirir. First tick artik yalnizca runtime heartbeat state'ini tamamlar; gercek market scan ayri process worker tarafindan calistirilir.

## Pure heartbeat first tick

`run_bot_first_tick_guarded` artik sunlari cagirmaz:

- `scan_market`
- Binance ticker veya kline fetch
- Paper Lab
- position/candidate scoring
- strategy/filter evaluation

Basarili first tick:

```json
{
  "requested_running": true,
  "bot_running": true,
  "engine_status": "running",
  "primary_runtime_problem": null,
  "tick_in_progress": false,
  "last_tick": "new timestamp"
}
```

Store'da hic scan yoksa `startup_pending_scan` placeholder olusturulur. Cached scan varsa sonucu ve timestamp'i korunur.

## Restore ve runtime truth

- Restore watchdog first tick kaniti olarak restore baslangicindan sonraki `last_tick` degerini kullanir.
- Yeni scan, first tick icin zorunlu degildir.
- Background scan hazirlanirken scan freshness icin sinirli startup grace uygulanir.
- First tick `ok` sonrasi main scheduler `engine_status=running` ve `primary_runtime_problem=None` degerlerini korur.

## Frontend polling

- Start API 200 dondugunde status read gecici hatasi bot start hatasi sayilmaz.
- Polling en fazla alti deneme ile devam eder.
- Backend sonradan running donerse UI aktif state'e gecer.
- Generic `API isteği başarısız` mesaji bot start failure olarak gosterilmez.

## Volume truth diagnostic

- Volume filtresi Binance `quoteVolume` yani `quoteVolume_USDT_24h` alanini kullanir.
- `10k`, `10K`, `10,000`, `10000`, `$10k`, `10k USDT` degerleri `10000` olarak parse edilir.
- Scan diagnostic `effective_min_quote_volume` ve low-volume orneklerini tasir.
- CoinFilter ekrani etkin minimum hacmi, elenen sayisini ve ornek coinlerin gercek 24 saatlik USDT hacmini gosterir.

## Kalite kapisi

- `scripts/level1_40_36_5_rev2_first_tick_heartbeat_audit.py`
- `docs/LEVEL1_40_36_5_REV2_FIRST_TICK_HEARTBEAT_AUDIT.json`
- `docs/LEVEL1_40_36_5_REV2_FIRST_TICK_HEARTBEAT_AUDIT.md`

Marker:

```text
LEVEL1_40_36_5_REV2_FIRST_TICK_HEARTBEAT_AUDIT_OK
```

## Degisen dosyalar

- `backend/services/bot_service.py`
- `backend/main.py`
- `backend/infrastructure/runtime/bot_loop_control.py`
- `backend/services/bot_runtime_truth_service.py`
- `backend/services/analysis_service.py`
- `backend/services/coin_universe_service.py`
- `frontend/js/app/bot.js`
- `frontend/js/pages/coinFilter.js`
- `scripts/level1_40_32_bot_restore_first_tick_audit.py`
- `scripts/level1_40_36_5_hard_cancel_bot_scan_worker_audit.py`
- `scripts/level1_40_36_5_rev2_first_tick_heartbeat_audit.py`
- `README.md`
- `todo.md`

## Test sonuclari

- `py -X pycache_prefix=.pycache_paket10_21_5_rev2 -m py_compile ...`: pass
- `py -c "import sys; sys.path.insert(0, 'backend'); import main; print('backend import ok')"`: pass, `backend import ok`
- `py scripts\level1_40_36_5_rev2_first_tick_heartbeat_audit.py`: pass, `status=ok`, `first_tick_scan_market_free=true`, `first_tick_ok_sets_running=true`, `volume_parse_10k_variants=true`, `volume_diagnostic_effective_min_10000=true`
- `py scripts\level1_40_36_5_hard_cancel_bot_scan_worker_audit.py`: pass, `status=ok`
- `py scripts\level1_40_36_4_bot_start_first_tick_timeout_audit.py`: pass, `status=ok`
- `py scripts\level1_40_36_3_bot_loop_cpu_throttle_audit.py`: pass, `status=ok`
- `py scripts\level1_40_36_2_status_field_sync_hotfix_audit.py`: pass, `status=ok`
- `py scripts\level1_40_36_1_bot_loop_none_numeric_hotfix_audit.py`: pass, `status=ok`
- `py scripts\level1_40_36_bot_start_and_coinfilter_save_stability_audit.py`: pass, `status=ok`
- `py scripts\level1_40_35_last_scan_contract_preservation_audit.py`: pass, `status=ok`
- `py scripts\level1_40_34_coinfilter_test_scan_timeout_audit.py`: pass, `status=ok`
- `py scripts\level1_40_32_bot_restore_first_tick_audit.py`: pass, `status=ok`
- `py scripts\level1_40_09_missing_endpoint_report.py`: pass, `true_blocker_count=0`
- `py scripts\level1_40_08_api_contract_diff.py --strict`: pass, `matched_call_count=94`, `missing_path_count=0`, `method_mismatch_count=0`
- `git diff --check`: pass; yalnizca mevcut Windows CRLF donusum uyarilari var
- `node --check frontend\js\app\bot.js`: calistirilamadi, Node PATH'te yok
- `node --check frontend\js\pages\coinFilter.js`: calistirilamadi, Node PATH'te yok

## Canli kabul

Deploy sonrasi 45 saniyelik bot start testinde:

- `last_tick` hemen dolmali.
- `engine_status=running` ve `primary_runtime_problem=null` olmali.
- `tick_in_progress=false` kalmali.
- CPU surekli `%100` olmamali.
- CoinFilter diagnostic etkin minimum `10000` ve gercek `quoteVolume_USDT_24h` degerlerini gostermeli.

Paket 10.22 ve Paket 10.23 baslatilmamistir.
