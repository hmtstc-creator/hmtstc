# Paket 10.21.5 Revize 5 — Safe CoinFilter Scan and Counters

## Amaç

CoinFilter test scan sırasında uvicorn CPU yükselmesini engellemek, CoinFilter algoritmasındaki satır bazlı eleme sayaçlarını netleştirmek ve dashboard live network alanının sadece filtreyi geçen coinleri göstermesini garanti altına almak.

## Ana Değişiklikler

- `/api/bot/coinfilter-test-scan` için güvenli limit eklendi: maksimum 350 coin.
- Aynı kullanıcı için eş zamanlı ikinci test scan engellendi.
- Test scan cache/cooldown eklendi; kısa aralıkta tekrar basılırsa yeni CPU işi başlatılmaz.
- Test scan timeout 8 saniyeye çekildi.
- CoinFilter lightweight skor eşiği artık `coin_filter.lightweight_score_min` üzerinden okunuyor.
- Skor eşiği altında kalan coinler artık `score_below_threshold` olarak sayılıyor; artık `WATCH` olarak sayım dışına kaçmıyor.
- `filter_rejection_counts` backend payload içine eklendi.
- CoinFilter sayfasındaki `Son Scan Elenen` kolonu artık satır `key` bazlı backend sayaçlarını okuyor.
- Dashboard live network sadece passed/candidate coinleri kullanıyor.
- Live network component her render’da hard reset yapmayacak şekilde mevcut instance üzerinde güncelleniyor.

## Kabul

- Dashboard/status 500 üretmez.
- CoinFilter test scan manuel çalışır, ikinci defa hızlı basılırsa cache/busy state döner.
- Minimum USDT hacim=1 ve minimum işlem=1 iken gizli likidite/işlem eşiği zorlanmaz.
- CoinFilter satırlarında elenen adetleri görünür.
- Uvicorn CPU uzun süre %100 kalmamalı.

## Audit

- `scripts/level1_40_39_safe_coinfilter_scan_and_counters_audit.py`
- Marker: `LEVEL1_40_39_SAFE_COINFILTER_SCAN_AND_COUNTERS_AUDIT_OK`
