# Paket 4 Decision Funnel Audit

## 1. Mevcut endpointler

Incelenen endpointler:

- `GET /api/dashboard`
- `GET /api/dashboard/bundle`
- `GET /api/bot/status`
- `GET /api/bot/last-scan`
- `GET /api/bot/scan-explain`
- `GET /api/bot/scan-debug`
- `GET /api/intelligence/tradeability-decision`
- `GET /api/intelligence/auto-bot-mode-decision`
- `GET /api/rules`
- `GET /api/settings`
- `GET /api/binance/market`

Dashboard ilk senkronizasyonda `/api/dashboard/bundle` kullanir; fallback durumda `/api/dashboard`, `/api/settings`, `/api/bot/status` ve `/api/rules` ayri cagrilir. Agir senkronizasyon katmani `/api/binance/market`, `/api/bot/last-scan`, intelligence karar endpointleri ve kullanici API izin bilgisini zaten toplar.

## 2. Dashboard tarafinda kullanilan mevcut veri

`frontend/js/app/api.js` icindeki `syncHeavyApiData()` asagidaki verileri `HMTSTC_DATA` icine yaziyor:

- `botScan`: `/api/bot/last-scan`
- `binanceMarket`: `/api/binance/market?limit=100&strict=false`
- `autoBotModeDecision61`: `/api/intelligence/auto-bot-mode-decision`
- `tradeabilityDecision60`: `/api/intelligence/tradeability-decision`
- `meApiConnection67`: `/api/users/me/api-connection`

`frontend/js/pages/dashboard.js` zaten `botScan`, `funnel_summary`, `botStatus`, `settings`, `rules`, `positions` ve intelligence karar verilerini okuyordu. Paket 4 icin yeni frontend API cagrisi gerekmedi.

## 3. Bot scan tarafinda bulunan mevcut alanlar

`/api/bot/last-scan` response'u karar hunisi icin yeterli temel alanlari donuyor:

- `time`, `scan_id`, `source`, `scan_mode`
- `scanned`, `universe_total_seen`
- `eligible_universe_count`, `universe_rejected_count`
- `candidates_count`, `rejected_count`
- `top_rejection_reason`
- `rejection_breakdown`
- `universe_rejection_breakdown`
- `candidates`
- `scan_rows`
- `funnel_summary`

`funnel_summary` ayrica `total_seen`, `eligible_universe`, `technical_passed`, `technical_rejected`, `active_models`, `final_candidate_count`, `opened_symbol`, `main_block_reason`, `main_block_label`, `breakdowns` ve son tick ozetini tasiyor.

## 4. Eksik alanlar

Mevcut endpoint strateji ve risk asamalarinin her coin icin kesin gecis/eleme kararini ayri alanlar olarak standartlastirmiyor. Bu nedenle dashboard UI bu iki asamayi mevcut `funnel_summary`, `candidates`, intelligence karar metinleri ve son scan red sebeplerinden turetilmis gorunurluk olarak sunar.

Eksik alanlar trading karari icin bloklayici degildir; Paket 4 kapsaminda karar mantigi degistirilmedigi icin mock veya yeni motor verisi uretilmedi.

## 5. Yeni endpoint gerekiyor mu?

Hayir. `GET /api/bot/decision-funnel` eklenmedi.

Mevcut `/api/bot/last-scan` endpoint'i read-only scan ozeti, adaylar ve eleme kirilimlarini yeterli seviyede sagliyor. Yeni endpoint eklemek ayni verinin backend tarafinda tekrar normalize edilmesine yol acar ve Paket 4 icin gerekli degildir.

## 6. Frontend-only cozum yeterli mi?

Evet. Dashboard mevcut `HMTSTC_DATA.botScan` payload'ini normalize ederek su UI modelini kurabiliyor:

- durum: `ok`, `empty`, `error`
- son guncelleme ve bot modu
- final sebep
- 6 karar hunisi asamasi
- en fazla 10 aday satiri
- en sik blok sebepleri

Gercek scan verisi yoksa UI bos state gosterir; hata varsa hata state gosterir. Mock veri uretilmez.

## 7. Nihai teknik karar

Paket 4 frontend-only tamamlandi. Yeni backend route, store yazimi, scan tetikleme, Binance istegi, order uretimi, strateji/filter/risk karari veya real-trade davranisi eklenmedi.
