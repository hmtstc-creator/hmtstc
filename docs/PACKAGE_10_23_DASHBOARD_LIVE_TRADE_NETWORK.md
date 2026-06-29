# Paket 10.23 Dashboard Live Trade Network

## Amac

Dashboard, mevcut cached backend verilerini kullanan yogun bir kripto terminal ekranina donusturuldu. Paket backend bot loop, scan worker, CoinFilter backend ve Paper Lab davranisini degistirmez.

## Dashboard yapisi

- Ust durum seridi: Backend API, bot, Binance API baglantisi ve calisma modu.
- Sol panel: Acik, Kapali, Otomatik ve Acil Stop kontrolleri; first tick ve worker ozeti; kural secimi.
- Orta panel: Canvas tabanli Live Trade Network.
- Sag panel: Bakiye, PnL, acik pozisyonlar ve son sinyal.
- Alt panel: CoinFilter son tarama ozeti, volume kontrati ve son olaylar.

Header bot kontrollerine bagimli degildir. Dashboard kontrolleri mevcut `HMTSTC_APP.startBot`, `stopBot`, ayar modu ve emergency modal akislarini kullanir.

## Live Trade Network

`frontend/js/components/liveTradeNetwork.js`:

- `requestAnimationFrame` ile cizilir.
- GIF, JPG veya PNG kullanmaz.
- Veri onceligi son scan adaylari, scan satirlari ve cached Binance market listesidir.
- Veri yoksa placeholder node ve `Henüz canlı tarama yok` mesaji gorunur.
- Bot kapaliyken hareket cok dusuk, acikken aktif, otomatik modda renk paleti farklidir.
- Dusuk FPS, gizli sekme veya reduced-motion durumunda otomatik degrade olur.

Dashboard render'i yeni fetch veya scan baslatmaz. Veriler mevcut `syncApiData` ve `syncHeavyApiData` store'undan okunur.

## CoinFilter ozeti

Gorunen alanlar:

- Toplam gorulen ve taranan coin
- Aday ve elenen coin
- Volume, liquidity, spread ve strategy red sayilari
- Son scan zamani
- `effective_min_quote_volume`
- `quoteVolume_USDT_24h` / USDT quote volume kontrati

Payload'da bulunmayan sayilar `N/A` olarak gosterilir.

## Mobil davranis

- `<= 900px`: kontroller, canvas, portfoy ve alt paneller tek kolon olur.
- `<= 640px`: Acil Stop gorunur ve sticky kalir; metrikler iki kolona iner.
- Canvas sabit mobil yukseklikte kalir ve yatay tasma olusturmaz.
- Log paneli kendi icinde scroll olur.

## Degisen dosyalar

- `frontend/index.html`
- `frontend/js/pages/dashboard.js`
- `frontend/js/components/liveTradeNetwork.js`
- `frontend/js/app/render.js`
- `frontend/css/dashboard-live-trade.css`
- `scripts/level1_40_37_dashboard_live_trade_network_audit.py`
- `docs/LEVEL1_40_37_DASHBOARD_LIVE_TRADE_NETWORK_AUDIT.json`
- `docs/LEVEL1_40_37_DASHBOARD_LIVE_TRADE_NETWORK_AUDIT.md`
- `docs/PACKAGE_10_23_DASHBOARD_LIVE_TRADE_NETWORK.md`
- `Paketler/paket10_23_dashboard.md`
- `README.md`
- `todo.md`

## Test sonuclari

- `py -m py_compile scripts\level1_40_37_dashboard_live_trade_network_audit.py`: pass
- `py scripts\level1_40_37_dashboard_live_trade_network_audit.py`: pass, `status=ok`, `dashboard_bot_controls_present=true`, `live_trade_network_component_present=true`, `dashboard_does_not_start_heavy_scan=true`, `mobile_responsive_css_present=true`
- `py scripts\level1_40_36_5_rev2_first_tick_heartbeat_audit.py`: pass, `status=ok`
- `py scripts\level1_40_36_5_hard_cancel_bot_scan_worker_audit.py`: pass, `status=ok`
- `py scripts\level1_40_36_4_bot_start_first_tick_timeout_audit.py`: pass, `status=ok`
- `py scripts\level1_40_36_3_bot_loop_cpu_throttle_audit.py`: pass, `status=ok`
- `py scripts\level1_40_09_missing_endpoint_report.py`: pass, `true_blocker_count=0`
- `py scripts\level1_40_08_api_contract_diff.py --strict`: pass, `matched_call_count=94`, `missing_path_count=0`, `method_mismatch_count=0`
- Statik frontend server: `index.html`, `liveTradeNetwork.js` ve `dashboard-live-trade.css` HTTP `200`
- `node --check`: calistirilamadi, Node PATH'te yok; `vm.Script` ile `bot.js`, `render.js`, `dashboard.js` ve `liveTradeNetwork.js` parse kontrolu pass
- Uygulama ici tarayici dogrulamasi: calistirilamadi, bu oturumda browser baglantisi mevcut degil
- `git diff --check`: pass; yalnizca Windows CRLF donusum uyarilari var

## Canli kabul

Deploy sonrasi Ctrl+F5 ile masaustu ve mobil gorunum kontrol edilmelidir. Dashboard acilisi yeni scan baslatmamali; bot kapaliyken canvas durgun, bot acikken hareketli ve otomatik modda farkli renk paletinde gorunmelidir.
