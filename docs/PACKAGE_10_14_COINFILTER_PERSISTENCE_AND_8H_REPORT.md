# Paket 10.14 CoinFilter Persistence and 8H Report

## 1. Paket amaci

Paket 10.14, CoinFilter ayar kaydinin uc noktada kanitlanmasini ve canli sistem icin 8 saatlik rapor altyapisini ekler.

Kritik hedef:

- Kullanici save payload'i
- Backend save response
- Runtime settings store echo
- GET refresh echo

ayni `coin_filter` degerini gostermelidir. Eski bundle veya partial settings payload'i son basarili CoinFilter kaydini ezemez.

## 2. CoinFilter persistence proof

Frontend `coinFilterSaveProof` alanini yazar:

```json
{
  "changedAt": "...",
  "payload": {},
  "response": {},
  "storeEcho": {},
  "refreshEcho": {},
  "persisted": true,
  "mismatchReason": ""
}
```

Eger payload, backend response, store echo veya refresh echo eslesmezse draft temizlenmez ve kullanici degeri ekranda korunur.

## 3. Backend store echo

`/api/settings` ve `/api/settings/coin-filter` save response'u su alanlari doner:

- `saved=true`
- `persisted=true/false`
- `source=settings_store`
- `coin_filter`
- `store_echo`
- `refresh_echo`

Bu alanlar frontend save zincirinin backend/store/refresh seviyesinde dogrulanmasi icin kullanilir.

## 4. Bundle overwrite guard

`syncApiData` icinde settings payload'i `applySettingsPayload` ile uygulanir.

Korunan durumlar:

- Local CoinFilter draft varsa backend payload onu ezmez.
- Partial/empty settings payload `coin_filter` alanini temizlemez.
- Son basarili save sonrasi eski bundle farkli `coin_filter` getirirse son persist edilen deger korunur ve diagnostic flag yazilir.

## 5. Bot no-trade reason funnel

Bot scan funnel rapor icin su alanlari tasir:

- `scan_total`
- `coinfilter_passed`
- `coinfilter_rejected`
- `strategy_signal_count`
- `karabasan_passed`
- `risk_passed`
- `final_trade_candidate_count`
- `trade_opened`
- `primary_no_trade_reason`
- `top_blockers`

Bu paket live monitor, Paper Lab progress, WebSocket veya SSE eklemez.

## 6. 8 saatlik rapor altyapisi

Yeni runtime store:

- `backend/eight_hour_report_store.json`
- Git'e alinmaz.
- `backend/eight_hour_report_store.example.json` sanitized template olarak tutulur.

Periyotlar:

- `00:00-08:00`
- `08:00-16:00`
- `16:00-00:00`

Timezone:

- `Europe/Bucharest`

Endpointler:

- `GET /api/reports/eight-hour/latest`
- `GET /api/reports/eight-hour/history`
- `POST /api/reports/eight-hour/generate`

Endpoint current last completed 8 saatlik blogu generate/cache eder; scheduler'a bagli degildir.

## 7. Degisen dosyalar

- `backend/routes/settings_routes.py`
- `backend/routes/bot_routes.py`
- `backend/routes/reports_routes.py`
- `backend/services/eight_hour_report_service.py`
- `backend/eight_hour_report_store.example.json`
- `backend/main.py`
- `frontend/js/app/api.js`
- `frontend/js/app/state.js`
- `frontend/js/pages/coinFilter.js`
- `scripts/level1_40_29_coinfilter_persistence_and_8h_report_audit.py`
- `docs/LEVEL1_40_29_COINFILTER_PERSISTENCE_AND_8H_REPORT_AUDIT.json`
- `docs/LEVEL1_40_29_COINFILTER_PERSISTENCE_AND_8H_REPORT_AUDIT.md`
- `docs/PACKAGE_10_14_COINFILTER_PERSISTENCE_AND_8H_REPORT.md`
- `.gitignore`
- `README.md`
- `todo.md`

## 8. Test sonuclari

- `py -X pycache_prefix=.pycache_paket10_14 -m py_compile backend\main.py backend\routes\settings_routes.py backend\routes\bot_routes.py backend\routes\reports_routes.py backend\services\eight_hour_report_service.py scripts\level1_40_29_coinfilter_persistence_and_8h_report_audit.py`: pass
- `py -c "import sys; sys.path.insert(0, 'backend'); import main; print('backend import ok')"`: pass
- `py scripts\level1_40_06_api_route_inventory.py`: pass, `route_count=896`
- `py scripts\level1_40_29_coinfilter_persistence_and_8h_report_audit.py`: pass, `status=ok`, `coinfilter_save_proof_present=true`, `coinfilter_bundle_overwrite_guard_present=true`, `eight_hour_report_latest_endpoint_present=true`, `eight_hour_report_generate_endpoint_present=true`, `previous_40_20_to_40_28_status_ok=true`
- `py scripts\level1_40_28_runtime_health_paperlab_user_resolution_audit.py`: pass, `status=ok`
- `py scripts\level1_40_27_runtime_health_paperlab_store_audit.py`: pass, `status=ok`
- `py scripts\level1_40_26_paperlab_hydration_stability_audit.py`: pass, `status=ok`
- `py scripts\level1_40_25_paperlab_persistence_audit.py`: pass, `status=ok`
- `py scripts\level1_40_09_missing_endpoint_report.py`: pass, `missing_path_count=0`, `method_mismatch_count=0`, `true_blocker_count=0`, `parser_gap_or_false_positive_count=0`
- `py scripts\level1_40_08_api_contract_diff.py --strict`: pass, `status=ok`, `matched_call_count=94`, `missing_path_count=0`, `method_mismatch_count=0`
- `node --check frontend\js\app\api.js`: calistirilamadi, Node PATH'te yok
- `node --check frontend\js\app\state.js`: calistirilamadi, Node PATH'te yok
- `node --check frontend\js\pages\coinFilter.js`: calistirilamadi, Node PATH'te yok
- Node REPL `vm.Script` parse kontrolu: pass, `frontend/js/app/api.js`, `frontend/js/app/state.js`, `frontend/js/pages/coinFilter.js`

## 9. Canli kabul testi

1. CoinFilter'da bir sayisal deger degistirilir.
2. Ayarlar kaydedilir.
3. Sayfa Ctrl+F5 ile yenilenir.
4. Degistirilen deger aynen gorunmelidir.
5. Eski bundle veya partial settings payload'i degeri eski haline dondururse Paket 10.14 fail sayilir.
6. `GET /api/reports/eight-hour/latest` cagrilir.
7. Response icinde `period`, `timezone=Europe/Bucharest`, `paper_lab`, `bot_decision`, `coinfilter` ve `no_trade_reasons` alanlari gorunmelidir.

## 10. Paket 11'e gecis karari

Paket 11'e sadece 40.20-40.29 zinciri `ok` olduktan, CoinFilter save proof canli Ctrl+F5 testinden gectikten ve 8 saatlik rapor endpointi canli runtime store'u olusturabildikten sonra gecilebilir.
