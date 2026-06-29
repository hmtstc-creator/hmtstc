# Paket 10.21.5 Hard Cancel Bot Scan Worker Revize 1

## Amac

Bot start sonrasi agir scan'in first tick watchdog timeout'undan sonra CPU tuketmeye devam etmesini engeller. First tick ile normal deep scan lifecycle'i ayrilmistir.

## Lightweight first tick

- Start endpoint scan veya first tick beklemeden doner.
- Scheduler ilk tick'te `run_bot_first_tick_guarded` calistirir.
- First tick `deep_analysis=False` ve en fazla 5 saniyelik market timeout kullanir.
- Paper Lab, coklu timeframe kline, deep technical analysis ve candidate execution ilk tick'te calismaz.
- Basarili snapshot `last_tick`, `last_scan`, `last_scan_time` ve `engine_status=running` alanlarini yazar.

## Ayrik scan worker

Normal deep tick `backend/infrastructure/runtime/bot_scan_worker.py` icinde daemon worker olarak calisir.

Runtime state:

```json
{
  "active_scan_worker": false,
  "scan_worker_started_at": null,
  "scan_worker_deadline_at": null,
  "scan_cancel_requested": false,
  "scan_worker_generation": 0
}
```

Worker 25 saniyelik deadline, cooperative cancel event ve bounded Binance request timeout kullanir. Scan, deep analysis, Paper Lab model/filter/strategy ve candidate dongulerinde cancel/deadline kontrolu vardir.

## Atomik generation guard

Worker sonucu `update_shadow_state` ile tek shadow lock altinda kontrol edilip yazilir. Su durumlardan biri varsa local worker sonucu store'a uygulanmaz:

- generation degismis
- `requested_running=false`
- `engine_status=failed/stopped/emergency_stopped`
- `scan_cancel_requested=true`
- cancel event set edilmis

Stop, emergency stop, yeni start ve first tick watchdog generation'i artirarak eski worker'i gecersiz kilar.

## CoinFilter cached view

- `/api/bot/last-scan` yalnizca store/cache okur.
- Dashboard bundle scan baslatmaz.
- Mevcut scan, yenileme veya bot start sirasinda temizlenmez.
- Scan yoksa `Henüz canlı tarama yok` mesaji gorunur.
- Manual test scan ayri aksiyon olarak korunur.

## Frontend start akisi

- Start 200 cevabi generic API error sayilmaz.
- Status 5 saniyelik araliklarla sinirli sayida poll edilir.
- Bekleme mesaji: `Bot başlatıldı. İlk piyasa taraması hazırlanıyor.`
- Timeout mesaji: `Bot ilk taramada zaman aşımına düştü. CPU kilidi önlendi.`

## Degisen dosyalar

- `backend/core/config.py`
- `backend/core/storage.py`
- `backend/main.py`
- `backend/routes/bot_routes.py`
- `backend/services/analysis_service.py`
- `backend/services/bot_service.py`
- `backend/services/paper_lab_service.py`
- `backend/services/position_service.py`
- `backend/services/market_service.py`
- `backend/infrastructure/runtime/bot_loop_control.py`
- `backend/infrastructure/runtime/bot_scan_worker.py`
- `frontend/js/app/bot.js`
- `frontend/js/app/state.js`
- `frontend/js/pages/coinFilter.js`
- `scripts/level1_40_36_3_bot_loop_cpu_throttle_audit.py`
- `scripts/level1_40_36_5_hard_cancel_bot_scan_worker_audit.py`
- `docs/LEVEL1_40_36_5_HARD_CANCEL_BOT_SCAN_WORKER_AUDIT.json`
- `docs/LEVEL1_40_36_5_HARD_CANCEL_BOT_SCAN_WORKER_AUDIT.md`
- `Paketler/paket10_21_5_revize1.md`
- `README.md`
- `todo.md`

## Test sonuclari

- `py -X pycache_prefix=.pycache_paket10_21_5 -m py_compile ...`: pass
- Lightweight first tick runtime probe: pass, `status=ok`, `deep_analysis=False`, `timeout_seconds=5`, `engine_status=running`, `tick_in_progress=false`
- `py scripts\level1_40_36_5_hard_cancel_bot_scan_worker_audit.py`: pass, `status=ok`, generation guard ve timeout cancel `true`
- `py scripts\level1_40_36_4_bot_start_first_tick_timeout_audit.py`: pass, `status=ok`
- `py scripts\level1_40_36_3_bot_loop_cpu_throttle_audit.py`: pass, `status=ok`
- `py scripts\level1_40_36_2_status_field_sync_hotfix_audit.py`: pass, `status=ok`
- `py scripts\level1_40_36_1_bot_loop_none_numeric_hotfix_audit.py`: pass, `status=ok`
- `py scripts\level1_40_36_bot_start_and_coinfilter_save_stability_audit.py`: pass, `status=ok`
- `py scripts\level1_40_35_last_scan_contract_preservation_audit.py`: pass, `status=ok`
- `py scripts\level1_40_34_coinfilter_test_scan_timeout_audit.py`: pass, `status=ok`
- `py scripts\level1_40_09_missing_endpoint_report.py`: pass, blocker yok
- `py scripts\level1_40_08_api_contract_diff.py --strict`: pass, `matched_call_count=94`, missing/mismatch yok
- Backend import: pass, `backend import ok`
- `git diff --check`: pass
- Frontend `node --check` komutlari calistirilamadi; Node bu makinenin PATH'inde yok.

## Canli kabul

Bot start sonrasi:

- HTTP start hizli doner.
- `last_tick` hafif snapshot ile dolar.
- Deep worker start request'inden bagimsizdir.
- Stop veya timeout sonrasi `active_scan_worker=false`, `scan_cancel_requested=true` olur.
- CPU surekli `%100` kalmaz ve stale worker stop state'ini geri alamaz.
- CoinFilter cached tabloyu korur veya `Henüz canlı tarama yok` gosterir.

Paket 10.22 ve Paket 10.23 baslatilmamistir.
