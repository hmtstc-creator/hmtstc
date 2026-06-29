# Paket 10.18 CoinFilter Final and Bot Pipeline Start

## 1. Paket amaci

Paket 10.18, CoinFilter sayfasini aday coin havuzu ekranina sadeleştirir ve yeni bot karar hattinin veri contract'ini başlatır.

CoinFilter artik:

- İşlem açmaz.
- Strateji seçmez.
- Paper Lab yönetmez.
- Sadece Binance USDT evreninden işlem adayı olabilecek coin havuzunu çıkarır.

## 2. Yeni sayfa yapisi

CoinFilter sayfa sirasi:

1. CoinFilter Kontrol Merkezi
2. Özet metrik kutuları
3. CoinFilter ayarları
4. Sistem sabit korumaları bilgi kutusu
5. CoinFilter karar hunisi
6. Eleme sebepleri
7. Son scan tablosu

Sayfadan kaldırılanlar:

- Aktif filtre envanteri
- Aktif strateji envanteri
- Rule Editor kaynaklı tablo
- Strateji koşul tablosu

## 3. Ayar davranisi

`min_quote_volume` ve `min_trade_count` hem frontend default hem backend `DEFAULT_COIN_FILTER` içine eklendi.

`excluded_symbols` textarea olarak gösterilir ve normalize edilir:

- Büyük harf
- Boşluk temizleme
- Tekrar eden sembolleri kaldırma
- Baş/son virgül temizleme

`scan_deep_analysis_limit` normal kullanıcı ana ayarı değildir; sadece admin/owner için gelişmiş satır olarak görünür.

## 4. Test scan endpoint

Yeni endpoint:

```http
GET /api/bot/coinfilter-test-scan?limit=1000
```

Davranış:

- Bot açık olmasını istemez.
- Gerçek emir açmaz.
- Strateji, Karabasan, risk veya execution çalıştırmaz.
- `last_scan` olarak kaydedebilir.
- Response içinde `test_scan=true` döner.

## 5. Pipeline contract

Scan response içinde yeni contract:

```json
{
  "pipeline": {
    "market_universe": {},
    "coinfilter": {},
    "strategy": { "status": "not_run_in_coinfilter_test" },
    "karabasan": { "status": "not_run_in_coinfilter_test" },
    "risk": { "status": "not_run_in_coinfilter_test" },
    "execution": { "status": "not_run_in_coinfilter_test" }
  }
}
```

Normal bot execution rewrite bu pakette yapılmadı.

## 6. Degisen dosyalar

- `frontend/js/pages/coinFilter.js`
- `frontend/js/app/settings.js`
- `backend/core/config.py`
- `backend/services/analysis_service.py`
- `backend/routes/bot_routes.py`
- `docs/PACKAGE_10_18_COINFILTER_FINAL_AND_BOT_PIPELINE_START.md`
- `docs/LEVEL1_40_33_COINFILTER_FINAL_PIPELINE_AUDIT.json`
- `docs/LEVEL1_40_33_COINFILTER_FINAL_PIPELINE_AUDIT.md`
- `scripts/level1_40_33_coinfilter_final_pipeline_audit.py`
- `README.md`
- `todo.md`

## 7. Test sonuclari

- `py -X pycache_prefix=.pycache_paket10_18 -m py_compile backend\core\config.py backend\services\analysis_service.py backend\routes\bot_routes.py scripts\level1_40_33_coinfilter_final_pipeline_audit.py`: pass
- `py -c "import sys; sys.path.insert(0, 'backend'); import main; print('backend import ok')"`: pass, `backend import ok`
- `py scripts\level1_40_33_coinfilter_final_pipeline_audit.py`: pass, `status=ok`, `coinfilter_test_scan_endpoint_present=true`, `test_scan_response_has_pipeline=true`, `pipeline_has_all_contract_sections=true`, `previous_40_20_to_40_32_status_ok=true`
- `py scripts\level1_40_06_api_route_inventory.py`: pass, `route_count=897`
- `py scripts\level1_40_32_bot_restore_first_tick_audit.py`: pass, `status=ok`
- `py scripts\level1_40_31_bot_restore_real_loop_audit.py`: pass, `status=ok`
- `py scripts\level1_40_30_bot_runtime_heartbeat_truth_audit.py`: pass, `status=ok`
- `py scripts\level1_40_29_coinfilter_persistence_and_8h_report_audit.py`: pass, `status=ok`
- `py scripts\level1_40_09_missing_endpoint_report.py`: pass, `missing_path_count=0`, `method_mismatch_count=0`, `true_blocker_count=0`, `parser_gap_or_false_positive_count=0`
- `py scripts\level1_40_08_api_contract_diff.py --strict`: pass, `matched_call_count=94`, `missing_path_count=0`, `method_mismatch_count=0`
- `node --check frontend\js\pages\coinFilter.js`: calistirilamadi, Node PATH'te yok
- `node --check frontend\js\app\settings.js`: calistirilamadi, Node PATH'te yok
- Node REPL `vm.Script` parse kontrolu: pass, `frontend/js/pages/coinFilter.js`, `frontend/js/app/settings.js`

Kontrol sirasinda `backend/eight_hour_report_store.json` ve `backend/paper_lab_store.json` runtime dosyalari olusmadi.

## 8. Canli kabul testi

Ctrl+F5 sonrasi:

- CoinFilter sayfasi açılır.
- Ayarlar kaybolmaz.
- Aktif filtre/strateji envanteri görünmez.
- Karar hunisi görünür.
- Son scan tablosunda coin bazlı elenme sebebi görünür.

Test scan:

```js
fetch('/api/bot/coinfilter-test-scan?limit=1000', {
  headers: {
    Authorization: `Bearer ${localStorage.getItem('hmtstc_token')}`
  }
}).then(r => r.json()).then(j => console.log(j))
```

Beklenen:

- `status=ok`
- `test_scan=true`
- `pipeline.market_universe`
- `pipeline.coinfilter`
- `pipeline.strategy.status=not_run_in_coinfilter_test`
- `pipeline.karabasan.status=not_run_in_coinfilter_test`
- `pipeline.risk.status=not_run_in_coinfilter_test`
- `pipeline.execution.status=not_run_in_coinfilter_test`

## 9. Paket 11'e gecis karari

Paket 11'e sadece 40.20-40.33 zinciri `ok` olduktan ve canlı CoinFilter test scan kabulü geçtikten sonra geçilebilir.
