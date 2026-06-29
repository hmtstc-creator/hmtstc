# Paket 10.21.5 Revize 5.2 — CoinFilter Single Source Hydration

## Amaç

CoinFilter ve Dashboard açılışta yeni scan başlatmadan son kayıtlı `last_scan` verisini okuyacak. CoinFilter satır ve özet sayaçları tek kaynak olarak `filter_rejection_counts` ve `last_scan` kontratını kullanacak.

## Kapatılan problemler

- Sayfa açılışında son scan verisinin görünmemesi.
- CoinFilter satır yanındaki “Son Scan Elenen” değerlerinin boş kalması.
- Dashboard bundle payload içinde tam `botScan` olmadığı için frontend’in heavy sync beklemesi.
- Dashboard live network’ün `passed !== false` gibi gevşek şartla aday göstermesi.
- Dashboard bundle içinde rule store backup taramasının sık çalışarak CPU riski oluşturması.
- Heavy sync içinde sayfa açılışında `/api/binance/market` çağrısının gereksiz tetiklenmesi.

## Davranış sözleşmesi

- Sayfa açılışı: `dashboard/bundle` içindeki cached `botScan` okunur.
- CoinFilter: `last_scan.filter_rejection_counts` satır yanındaki sayaçların tek kaynağıdır.
- Manuel Test Scan: sadece butona basılınca `/api/bot/coinfilter-test-scan` çalışır.
- Kaydet: settings kaydeder; scan başlatmaz.
- Dashboard network: sadece `passed === true` coinleri gösterir.
- Heavy sync: cached last scan okuyabilir ama otomatik Binance market fetch başlatmaz.

## Değişen dosyalar

- `backend/routes/dashboard_routes.py`
- `backend/services/rule_engine.py`
- `frontend/js/app/api.js`
- `frontend/js/pages/coinFilter.js`
- `frontend/js/pages/dashboard.js`
- `scripts/level1_40_39_2_coinfilter_single_source_hydration_audit.py`
- `docs/LEVEL1_40_39_2_COINFILTER_SINGLE_SOURCE_HYDRATION_AUDIT.json`
- `docs/LEVEL1_40_39_2_COINFILTER_SINGLE_SOURCE_HYDRATION_AUDIT.md`

## Test sonucu

- `LEVEL1_40_39_2_COINFILTER_SINGLE_SOURCE_HYDRATION_AUDIT_OK`
- Backend import OK
- Python compile OK
- JS syntax OK
