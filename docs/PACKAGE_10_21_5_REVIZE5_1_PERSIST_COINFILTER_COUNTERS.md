# Paket 10.21.5 Revize 5.1 — Persist CoinFilter Counters

## Amaç

CoinFilter test scan response içinde doğru üretilen sayaçların `shadow_store.json -> users.<user>.last_scan` içine eksiksiz yazılması sağlandı.

## Düzeltilen sorun

Canlı testte `/api/bot/coinfilter-test-scan?limit=1000` response içinde `filter_rejection_counts` doluydu; fakat store içindeki `last_scan.filter_rejection_counts` null/boş kalıyordu. Sebep `normalize_shadow_state()` içindeki `last_scan` whitelist alanlarının Revize 5 sayaç ve diagnostic alanlarını korumamasıydı.

## Korunan alanlar

- `filter_rejection_counts`
- `volume_rejection_diagnostics`
- `liquidity_rejection_diagnostics`
- `rejection_summary`
- `scan_rows`
- `candidates`
- `pipeline`

## Kabul

- Test scan sonrası store içinde `filter_rejection_counts` dolu kalır.
- CoinFilter sayfasındaki “Son Scan Elenen” kolonu backend store verisinden sayıları okuyabilir.
- Hacim/işlem adedi 1 ise `min_quote_volume=0`, `min_trade_count=0` korunur.
