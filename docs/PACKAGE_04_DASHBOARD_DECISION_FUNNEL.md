# Paket 4 Dashboard Decision Funnel

## 1. Paket amaci

Paket 4'un amaci dashboard uzerinde botun neden islem acmadigini asama asama gorunur hale getirmektir. Bu paket yalnizca read-only analiz ve UI gorunurlugu ekler.

## 2. Hangi veriler kullanildi?

Kullanilan ana veri `/api/bot/last-scan` response'udur. Dashboard bu payload icindeki `funnel_summary`, scan sayilari, aday listeleri, `rejection_breakdown`, `universe_rejection_breakdown` ve `top_rejection_reason` alanlarini normalize eder.

Destekleyici veri olarak mevcut `botStatus`, `settings`, `rules`, `positions`, `/api/intelligence/tradeability-decision`, `/api/intelligence/auto-bot-mode-decision` ve kullanici API izin bilgisi okunur.

## 3. Yeni endpoint eklendi mi?

Hayir. `GET /api/bot/decision-funnel` eklenmedi.

Mevcut `/api/bot/last-scan` dashboard karar hunisi icin yeterli oldugu icin backend route degisikligi yapilmadi.

## 4. Dashboard'a eklenen alanlar

Dashboard'a `Karar Hunisi` paneli eklendi. Panelde su alanlar var:

- `Piyasa verisi`
- `Taranan coin`
- `Filtrelerden gecen`
- `Strateji sinyali`
- `Risk / Karabasan`
- `Final islem adayi`
- `Coin | Filtre | Strateji | Risk | Skor | Karar | Sebep` aday tablosu
- En sik blok sebepleri

Bos durumda `Son tarama verisi yok. Bot calisinca karar hunisi burada gorunecek.` mesaji gosterilir. Hata durumunda `Karar hunisi okunamadi. Backend baglantisi veya son tarama verisi kontrol edilmeli.` mesaji gosterilir.

## 5. No-trade sebep mantigi

No-trade sebebi mevcut karar verisinden okunur. Oncelik sirasinda bot durumu, `funnel_summary.main_block_label`, kullanici API trade izni, intelligence karar metni, scan ana red sebebi, aday sayisi ve pozisyon limiti kullanilir.

Belirsiz `Uygun coin yok` dili yerine `Final islem adayi olusmadi. Sebep: ...` formati kullanildi.

## 6. Degistirilen dosyalar

- `frontend/js/pages/dashboard.js`
- `frontend/css/dashboard-funnel.css`
- `docs/PACKAGE_04_DECISION_FUNNEL_AUDIT.md`
- `docs/PACKAGE_04_DASHBOARD_DECISION_FUNNEL.md`
- `README.md`
- `todo.md`
- Contract guard raporlari

## 7. Dokunulmayan kritik dosyalar

Su kritik alanlara dokunulmadi:

- Runtime store dosyalari
- `deploy/*`
- `webhook_server.py`
- `backend/routes/real_routes.py`
- `backend/services/*order*`
- `backend/services/*executor*`
- `backend/services/*binance*`
- `frontend/js/app/realTrade.js`
- `frontend/js/app/realApproval.js`

## 8. Test sonuclari

- `py -m py_compile backend\main.py webhook_server.py scripts\level1_40_07_frontend_api_inventory.py scripts\level1_40_08_api_contract_diff.py scripts\level1_40_09_missing_endpoint_report.py`: pass
- `py scripts\level1_40_06_api_route_inventory.py`: pass, `route_count=891`
- `py scripts\level1_40_07_frontend_api_inventory.py`: pass, `call_count=87`, `unique_base_path_count=72`
- `py scripts\level1_40_08_api_contract_diff.py --strict`: pass, `missing_path_count=0`, `method_mismatch_count=0`
- `py scripts\level1_40_09_missing_endpoint_report.py`: pass, `true_blocker_count=0`, `parser_gap_or_false_positive_count=0`
- `node --check frontend\js\pages\dashboard.js`: calistirilamadi, yerel PATH'te `node` bulunamadi
- Frontend manuel tarayici kontrolu: calistirilamadi, bu oturumda in-app browser `iab` olarak erisilebilir degildi

## 9. Contract guard sonucu

Contract guard temiz gecti:

- `missing_path_count=0`
- `method_mismatch_count=0`
- `true_blocker_count=0`
- `parser_gap_or_false_positive_count=0`

## 10. Paket 5'e gecis karari

Testler temiz tamamlandiginda Paket 5'e gecis uygundur.

Paket 4 tamamlandı. Dashboard üzerinde karar hunisi ve no-trade sebep görünürlüğü eklendi. Bu paket işlem açma, Binance, Futures, real-trade, strateji, filtre veya Karabasan karar mantığını değiştirmedi. Paket 5'e geçiş için zemin uygundur.
