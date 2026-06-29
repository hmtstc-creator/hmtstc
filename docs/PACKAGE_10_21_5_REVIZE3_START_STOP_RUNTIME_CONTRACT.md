# Paket 10.21.5 Revize 3 Start Stop Runtime Contract

## Amac

Bot start, stop ve read endpointleri CPU yogun background scan davranisindan ayrildi.

Temel sozlesme:

- Start: state'e heartbeat yazar ve hizli doner.
- Stop: tum worker niyetlerini iptal eder ve hizli doner.
- Status: cached state okur; yalnizca stale worker kaydini temizleyebilir.
- Dashboard bundle: cached/store verisini okur, worker baslatmaz.

## Merkezi runtime flagleri

`backend/infrastructure/runtime/bot_runtime_flags.py`:

```python
AUTO_SCAN_ON_BOT_START = False
AUTO_SCAN_ON_STATUS_READ = False
AUTO_SCAN_ON_DASHBOARD_READ = False
ENABLE_BACKGROUND_SCAN_WORKER = False
```

Eksik settings degeri bu flagleri acmaz. Background worker ancak gelecekte acik bir paket ve kalite kapisiyla etkinlestirilebilir.

## Start sozlesmesi

`POST /api/bot/start`:

- `ensure_bot_loop_running` cagirmaz.
- Thread/process/scan/Paper Lab baslatmaz.
- `requested_running=true`
- `bot_running=true`
- `engine_status=running`
- `primary_runtime_problem=null`
- `tick_in_progress=false`
- `active_scan_worker=false`
- `scan_cancel_requested=false`
- `last_tick` ve update timestamp alanlarini doldurur.
- Ilk cagri `status=running`, tekrar cagri `status=already_running` doner.
- Runtime modu `heartbeat_only` olarak raporlanir.

Backend restart sirasinda requested state varsa ayni heartbeat-only state geri yuklenir; scheduler veya scan worker baslamaz.

## Stop sozlesmesi

`POST /api/bot/stop`:

- `requested_running=false`
- `bot_running=false`
- `engine_status=stopped`
- `primary_runtime_problem=null`
- `tick_in_progress=false`
- `active_scan_worker=false`
- `scan_cancel_requested=true`
- `next_tick_not_before=null`
- Worker PID/deadline alanlari temizlenir.

Process terminate grace 1 saniyedir; zorunlu terminate ve kill adimlari toplamda iki saniyeyi asmayacak sekilde sinirlanir.

## Status ve stale cleanup

Status yeni worker baslatmaz ve health history yazmaz. Persisted state `active_scan_worker=true` derken canli process yoksa veya deadline gectiyse:

- worker state temizlenir,
- `scan_cancel_requested=true` olur,
- `primary_runtime_problem=stale_scan_worker_cleared` yazilir.

Replacement worker baslatilmaz.

## Frontend

- Start 200 sonrasi `Bot açıldı. Durum doğrulanıyor.` mesaji gorunur.
- Gecici status okuma hatasi warning olarak loglanir ve yeniden denenir.
- Start/stop pending iken ikinci komut engellenir.
- Pending guard en gec 5 saniyede temizlenir.
- Dashboard bot butonlari pending sirasinda disabled olur.

## Call graph siniflandirmasi

- `/api/bot/start`: `COMMAND_START`, heartbeat-only.
- `/api/bot/stop`: `COMMAND_STOP`, cancel-and-clear.
- `/api/bot/status`: `READ_ONLY`, stale cleanup izinli.
- `/api/dashboard/bundle`: `READ_ONLY`.
- `/api/bot/tick`, scan debug/test endpointleri: `MANUAL_SCAN`.
- `main.bot_loop`: `LEGACY_AUTO_SCAN`, merkezi flag ile kapali.
- `start_scan_worker`: `SCHEDULED_SCAN`, merkezi flag ile kapali.

Detayli tetik noktalari `docs/LEVEL1_40_36_5_REV3_START_STOP_RUNTIME_CONTRACT_AUDIT.md` icindedir.

## Degisen dosyalar

- `backend/main.py`
- `backend/routes/bot_routes.py`
- `backend/services/bot_service.py`
- `backend/services/bot_runtime_truth_service.py`
- `backend/infrastructure/runtime/bot_loop_control.py`
- `backend/infrastructure/runtime/bot_scan_worker.py`
- `backend/infrastructure/runtime/bot_runtime_flags.py`
- `frontend/js/app/state.js`
- `frontend/js/app/bot.js`
- `frontend/js/pages/dashboard.js`
- `frontend/css/dashboard-live-trade.css`
- `scripts/level1_40_36_bot_start_and_coinfilter_save_stability_audit.py`
- `scripts/level1_40_36_3_bot_loop_cpu_throttle_audit.py`
- `scripts/level1_40_36_4_bot_start_first_tick_timeout_audit.py`
- `scripts/level1_40_36_5_rev2_first_tick_heartbeat_audit.py`
- `scripts/level1_40_36_5_rev3_start_stop_runtime_contract_audit.py`
- `scripts/level1_40_37_dashboard_live_trade_network_audit.py`
- `README.md`
- `todo.md`

## Test sonuclari

- Python compile: pass.
- Backend import: pass, `backend import ok`.
- Revize3 audit: pass, `LEVEL1_40_36_5_REV3_START_STOP_RUNTIME_CONTRACT_AUDIT_OK`.
- Route runtime probe: first start `running`, second start `already_running`, stop `stopped`; state contract pass.
- 40.34-40.36.5 audit zinciri: pass; base, 40.36.1, 40.36.2, 40.36.3, 40.36.4, hard-cancel ve Revize2 status `ok`.
- 40.37 dashboard audit: pass, `LEVEL1_40_37_DASHBOARD_LIVE_TRADE_NETWORK_AUDIT_OK`.
- 40.09 missing endpoint: pass, `true_blocker_count=0`.
- 40.08 strict API contract: pass, `matched_call_count=94`, `missing_path_count=0`, `method_mismatch_count=0`.
- Frontend JavaScript dosyalari Node `vm.Script` ile parse edildi: pass.
- `node --check` calistirilamadi; Node CLI PATH'te yok.

## Canli kabul

CPU yuzdeleri ve gercek worker process davranisi deploy sonrasi VPS'te olculmelidir. Lokal kalite kapisi CPU yuzdesini kanitlamaz.

Beklenen start state:

```text
requested_running=true
bot_running=true
engine_status=running
primary_runtime_problem=null
tick_in_progress=false
active_scan_worker=false
scan_cancel_requested=false
```

Beklenen stop state:

```text
requested_running=false
bot_running=false
engine_status=stopped
primary_runtime_problem=null
tick_in_progress=false
active_scan_worker=false
scan_cancel_requested=true
```
