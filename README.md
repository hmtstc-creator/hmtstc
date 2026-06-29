# HMTSTC MASTER README
## Spot-First Trading Intelligence Platform — Ürün, Mimari, Sayfa Yapısı ve Yönetim Ansiklopedisi

**Doküman amacı:** Bu README, HMTSTC projesinin var oluş mantığını, ürün hedefini, sayfa mimarisini, backend yapısını, veri ilişkilerini, işlem motorunu, yönetim metotlarını, güvenlik kararlarını ve faz bazlı ürünleşme yolunu tek merkezde anlatır.

**Kritik not:** Önceki revizyonlarda REV13 son dosya adı olarak oluştu; fakat REV13 içeriği büyük ölçüde “REV10’dan devam” diyen meta dokümandı. Bu MASTER README, o eksikliği düzelten ana referans dokümandır. Geliştirme ekibi README olarak bunu kullanmalıdır.

---

# Current Architecture Baseline

Current architecture:

- Static frontend is served from `frontend/index.html`.
- Frontend uses modular page files under `frontend/js/pages/` and app modules under `frontend/js/app/`.
- `frontend/js/config.js` selects the API base, and `frontend/js/app/api.js` sends `/api` requests with Bearer token auth.
- FastAPI backend includes auth, settings, users, rules, Binance-facing, guarded real-trade, production and quality routes.
- Runtime JSON stores are local-only and ignored by Git.
- Example store files are tracked only as sanitized templates.
- Live trading behavior must only be changed in dedicated safety packages.
- Paket 3 API contract guard raporları frontend API çağrılarını backend route yüzeyiyle karşılaştırır, runtime store policy ihlallerini izler ve endpoint metadata stringlerini gerçek API çağrısı saymaz.
- Paket 4 dashboard karar hunisi, mevcut `/api/bot/last-scan` verisini frontend-only normalize ederek botun neden işlem açmadığını görünür kılar; trading, Binance, Futures, real-trade, strateji, filtre ve risk karar mantığı değişmez.
- Paket 5 mutating endpoint safety audit, frontend inventory içindeki mutating çağrıları güvenlik kategorilerine ayırır ve `scripts/level1_40_10_mutating_endpoint_safety_audit.py` ile live-trade özel inceleme kapısı sağlar.
- Paket 6 real-trade manual review matrix, Paket 5'in `CRITICAL_REAL_TRADE` listesini read-only owner onay beklentisi ve risk tipi matrisine dönüştürür; real-trade runtime davranışını değiştirmez.
- Paket 7 owner approval contract audit, Paket 6 matrisindeki owner onay, readiness, dry-run, audit gerekçesi ve emergency lock beklentilerini `scripts/level1_40_12_owner_approval_contract_audit.py` ile kalite kapısına dönüştürür.
- Paket 8 rule selection persistence, Dashboard Strateji / Filtre seçimlerini explicit backend seçim, kullanıcı draft'ı ve aktif fallback olarak ayırır; Paper Lab save response'unu doğrulamadan draft temizlemez.
- Paket 9 rule backend stability, `/api/rules/activate-paper-lab` ve rule save/get/delete endpointlerinde payload validation, net HTTP detail, response contract ve audit/log izolasyonunu güçlendirir; Paper Lab model matematiğini değiştirmez.
- Paket 10 system status and runtime store, Dashboard `Sistem Durum Seridi` ile Backend API, Bot, Karabasan, Paper Lab, Rule Store ve Binance durumunu gorunur yapar; API hata siniflandirmasini ve manuel onayli rule_store restore guard'ini ekler.
- Paket 10.1 auth 401 state guard, logout/auth 401 durumunu backend offline'dan ayirir, `HMTSTSTC_APP` typo riskini kapatir ve 401 sonrasi son basarili rule listesini korur.
- Paket 10.2 Paper Lab state truth, Auto Paper Lab'i `apiReady/apiSyncReady` yerine gercek `/api/rules` cevabina baglar, bundle rules eksikliginde son basarili rule listesini korur ve 40.17 audit kapisini ekler.
- Paket 10.3 auth store atomic write, eszamanli login/logout yazimlarinda benzersiz tmp dosya ve RLock kullanir, login double-submit guard ekler ve 40.18 audit kapisini getirir.
- Paket 10.4 mutation abort isolation, CoinFilter/Rules/Paper Lab mutation isteklerini sync ve agir endpoint abortlarindan ayirir, `request_aborted` durumunu Backend API offline saymaz ve 40.19 audit kapisini ekler.
- Paket 10.5 live startup rules hydration, startup polling'i yavaslatir, heavy sync'i login/acilis sonrasi erteler, dashboard bundle fail olsa bile `/api/rules` ve `/api/settings` fallback hydration ile ekranin bos kalmasini engeller ve 40.20 audit kapisini ekler.
- Paket 10.6 auth restore truth, localStorage token varligini auth truth saymaz, acilista `/api/auth/me` ile token dogrular, restore bitmeden sync baslatmaz ve 40.21 audit kapisini ekler.
- Paket 10.7 CoinFilter / Rules / Paper Lab, CoinFilter inputlarini local draft ile korur, Dashboard rule selection'in bos/eksik payload sonrasi tumu seciliye donmesini engeller, Paper Lab son calisma durumunu Stratejiler sayfasinda gorunur yapar, rules save E2E selection proof zincirini kanitlar ve 40.22 audit kapisini ekler.
- Paket 10.8 Rules Selection / Paper Lab Independence, Dashboard active rule selection kaydini `/api/rules/selection` ile Paper Lab'den ayirir, Paper Lab'in Dashboard secimlerini degistirmesini engeller, Paper Lab'i tum eligible filtre/strateji laboratuvari olarak calistirir ve 40.23 audit kapisini ekler.
- Paket 10.9 Paper Lab autonomous research engine, Paper Lab runtime lifecycle alanlarini `idle/running/completed/failed` olarak ayirir, selected ids kullanmadan tum enabled filtre/strateji kombinasyonlarini tekrar tekrar calistirabilir hale getirir ve 40.24 audit kapisini ekler.
- Paket 10.10 Paper Lab persistent runtime store, Paper Lab arastirma run'larini `backend/paper_lab_store.json` kalici runtime store'una atomic yazar, reload/restart/deploy sonrasi backend status ile hydrate eder, fingerprint stale uyarisi verir ve 40.25 audit kapisini ekler.
- Paket 10.11 Paper Lab hydration stability, kalici Paper Lab status endpoint'ini 60 saniye throttle ve in-progress guard ile sinirlar, bundle icindeki `paper_lab_status` bilgisini oncelikli kullanir, rules render'ini status loading'den izole eder ve 40.26 audit kapisini ekler.
- Paket 10.12 Runtime Health Paper Lab Store Link, `/health/ops` runtime health icindeki `last_paper_lab` kaynagini `backend/paper_lab_store.json` persistent run kaydina baglar, legacy fallback'i korur ve 40.27 audit kapisini ekler.
- Paket 10.13 Runtime Health Paper Lab User Resolution, auth context olmayan `/health/ops` icin Paper Lab store'daki tum kullanicilar arasindan en guncel run'i bulur, `username` alanini health ciktisina ekler ve 40.28 audit kapisini getirir.
- Paket 10.14 CoinFilter Persistence and 8H Report, CoinFilter save payload/backend response/store echo/refresh echo zincirini kanitlar, eski bundle overwrite riskini engeller, bot no-trade reason funnel alanlarini raporlanabilir yapar ve scheduler'siz 8 saatlik rapor endpointleriyle 40.29 audit kapisini ekler.
- Paket 10.15 Bot Runtime Heartbeat Truth, persistent `requested_running` ile canli loop heartbeat'ini ayirir, stale tick/scan durumunda efektif `bot_running=false` gosterir, backend restart sonrasi guvenli paper/shadow loop restore ekler ve 40.30 audit kapisini getirir.
- Paket 10.16 Bot Restore Real Loop, restore sirasinda sahte heartbeat yazilmasini engeller, startup restore ve manuel start'i ortak `ensure_bot_loop_running` helper'ina baglar, task alive kontrolunu gercek thread referansi ve taze heartbeat ile yapar ve 40.31 audit kapisini ekler.
- Paket 10.17 Bot Restore First Tick, restore basarisini thread alive yerine ilk gercek tick/scan kanitina baglar, `waiting_first_tick` ve `restore_no_first_tick` durumlarini ayirir, bot loop diagnostic loglarini ekler ve 40.32 audit kapisini getirir.
- Paket 10.18 CoinFilter Final and Bot Pipeline Start, CoinFilter sayfasini aday coin havuzu ekranina sadeleştirir, bot kapali olsa da calisan `/api/bot/coinfilter-test-scan` endpointini ekler, scan response'una pipeline contract'i koyar ve 40.33 audit kapisini getirir.
- Paket 10.19 CoinFilter Test Scan Timeout Fix, test scan yolunda deep teknik analizi kapatir, lightweight 24h ticker analizini korur ve 40.34 audit kapisini getirir.
- Paket 10.20 Last Scan Contract Preservation, test scan pipeline ve universe alanlarini storage normalizasyonunda korur, eski runtime store icin guvenli repair uygular ve 40.35 audit kapisini getirir.
- Paket 10.21 Bot Start and CoinFilter Save Stability, save timeout/AbortError ayrimini duzeltir, scan settings proof ekler, bot requested state ile gercek loop state'ini ayirir ve 40.36 audit kapisini getirir.
- Paket 10.21.1 Bot Loop None Numeric Hotfix, bozuk market/indicator sayilarini coin-level reject eder, traceback ile gercek loop hata sebebini korur ve 40.36.1 audit kapisini getirir.
- Paket 10.21.2 Status Field Sync Hotfix, scan tamamlaninca `last_scan_time` alanini `last_scan.time` ile senkronlar, bot status ve Dashboard fallback davranisini sabitler ve 40.36.2 audit kapisini getirir.
- Paket 10.21.3 Bot Loop CPU Throttle, stopped kullanicida scheduler/restore/scan isini sifirlar, tick araligi ve hata backoff'u uygular, deep analiz limitini 8'e indirir ve 40.36.3 audit kapisini getirir.
- Paket 10.21.4 Bot Start First Tick Timeout, start endpointini first tick'ten ayirir, scan/deep analysis deadline uygular, stuck tick lock'unu finally ile temizler ve 40.36.4 audit kapisini getirir.
- Paket 10.21.5 Hard Cancel Bot Scan Worker, first tick'i lightweight snapshot ile sinirlar, deep scan'i generation/cancel guard'li ayri worker'a tasir, stale worker runtime write'ini atomik olarak engeller, CoinFilter cached view'i korur ve 40.36.5 audit kapisini getirir.
- Paket 10.21.5 Revize 2 First Tick Heartbeat, startup first tick'inden tum market fetch ve analiz islerini kaldirir, restore kanitini saf heartbeat `last_tick` alanina baglar, quoteVolume tabanli 10k hacim parser/diagnostic dogrulamasini ekler ve 40.36.5 Rev2 audit kapisini getirir.

---

# 1. Ürünün Var Oluş Mantığı

HMTSTC klasik anlamda sadece “al-sat botu” değildir. Ürün, kullanıcının kendi Binance hesabını API ile bağlayıp, kendi seçtiği sermaye sınırı içinde spot piyasada otomatik işlem yapmasını sağlayan, aynı anda strateji test laboratuvarı ve piyasa risk karar motoru barındıran bir trading intelligence platformudur.

İlk hedef para kazandırma ihtimalini en hızlı şekilde başlatmaktır. Bu yüzden ilk canlı ürün kapsamı Futures değil, **Spot Money Pilot** olmalıdır. Futures karmaşıklığı daha yüksektir; liquidation, margin, leverage, funding fee gibi ek riskler içerir. Spot tarafı ise sermaye sınırı daha net kontrol edilebildiği için ilk canlı ürün için daha uygundur.

HMTSTC’nin var oluş nedeni üç ana ihtiyaca dayanır:

1. **Kullanıcı adına kontrollü spot işlem açmak:** Kullanıcı API bağlar, bot bütçesi tanımlar, bot yalnızca bu bütçe sınırları içinde çalışır.
2. **Strateji ve filtreleri sistemli şekilde test etmek:** Admin/Ahmet Paper Lab içinde filtre ve strateji kombinasyonlarını sanal bütçelerle test eder.
3. **Piyasa koşullarına göre botu açıp kapatmak:** Karabasan motoru BTC trendi, piyasa riski, likidite, volatilite ve ileride makro/haber verileriyle botun işlem açmasına izin verir veya engeller.

---

# 2. Nihai Ürün Tanımı

HMTSTC, kullanıcı bazlı ayarlar, Binance Spot bağlantısı, risk motoru, emir yaşam döngüsü, Paper Lab, Karabasan ve yönetim panellerinden oluşan çok katmanlı bir web platformudur.

Ürün şu parçaların birleşimidir:

```text
HMTSTC
├── Kullanıcı Uygulaması
│   ├── Dashboard
│   ├── Ayarlar
│   ├── Pozisyonlar
│   ├── İşlem Geçmişi
│   └── Risk Sözleşmesi
│
├── Admin / Ahmet Uygulaması
│   ├── Admin Dashboard
│   ├── Kullanıcı Yönetimi
│   ├── Paper Lab
│   ├── Karabasan Studio
│   ├── Strateji / Filtre Yönetimi
│   ├── Risk İzleme
│   ├── Güvenlik Konsolu
│   └── Emergency Control
│
├── Trading Core
│   ├── Binance Spot Connector
│   ├── Strategy Engine
│   ├── Filter Engine
│   ├── Risk Engine
│   ├── Order Lifecycle Engine
│   ├── Position Manager
│   ├── Trade Journal
│   └── PnL Engine
│
├── Intelligence Core
│   ├── Paper Lab
│   ├── Karabasan V0/V1
│   ├── Learning Engine
│   ├── Model Registry
│   └── Feature Store
│
├── Security Core
│   ├── Auth
│   ├── RBAC
│   ├── Tenant Isolation
│   ├── Secret Encryption
│   ├── Audit Log
│   ├── Rate Limit
│   └── Emergency Stop
│
└── Operations Core
    ├── Monitoring
    ├── Alerting
    ├── Backup
    ├── Restore
    ├── Incident Runbook
    └── Deployment Pipeline
```

---

# 3. Öncelik Kararı

Geliştirme sırası kesinlikle aşağıdaki gibi olmalıdır:

```text
1. Spot Money Pilot
2. Paper Lab paralel analiz
3. Karabasan V0 → V1
4. Çok kullanıcılı kiralama/paket yapısı
5. Futures Paper/Testnet
6. Futures Admin Pilot
7. Futures VIP kullanıcı açılımı
```

Bu kararın gerekçesi:

- En hızlı gelir ihtimali Spot MVP ile başlar.
- Paper Lab canlı sistemi bozmadan model üretir.
- Karabasan önce basit risk kapısı olur, sonra gelişir.
- Futures en yüksek riskli modüldür, en sona bırakılır.

---

# 4. Kullanıcı Rolleri

## 4.1 Normal Kullanıcı

Normal kullanıcı platformu kiralayan kişidir. Kendi Binance API bilgisini girer, bot bütçesini belirler, risk sözleşmesini kabul eder ve Dashboard üzerinden botu yönetir.

Normal kullanıcı şunları yapabilir:

- Binance API key/secret eklemek.
- API bağlantısını test etmek.
- Bot için ayrılacak USDT bütçesini tanımlamak.
- Pozisyon başı işlem tutarını belirlemek.
- Bot modunu seçmek: Kapalı, Açık, Otomatik.
- Kendi filtre/strateji seçimlerini görmek ve izin verilen sınırlar içinde değiştirmek.
- Açık pozisyonları görmek.
- Günlük/haftalık PnL görmek.
- İşlem geçmişini dışa aktarmak.
- Risk sözleşmesini kabul etmek.

Normal kullanıcı şunları göremez:

- Başka kullanıcıların verileri.
- Admin Paper Lab sonuçları.
- Sistem secret bilgileri.
- Model Registry admin kararları.
- Karabasan global parametre yönetimi.
- Diğer kullanıcıların API durumları.

## 4.2 Admin / Ahmet

Admin, platformun sahibi/yöneticisidir. Ahmet hesabı admin rolünün ana temsilidir.

Admin şunları yapabilir:

- Tüm kullanıcıların durumunu izlemek.
- Kullanıcıları aktif/pasif yapmak.
- Paket ve kiralama sürelerini yönetmek.
- Paper Lab modellerini çalıştırmak.
- Strateji ve filtre kombinasyonlarını test etmek.
- Karabasan parametrelerini görmek ve yönetmek.
- Risk olaylarını izlemek.
- Emergency Stop çalıştırmak.
- Kullanıcıların işlem durumunu okumak.
- Ancak API secret’ları düz metin olarak göremez.

Admin’in yapamayacağı şeyler:

- Kullanıcı API secret bilgisini açık görmek.
- Kullanıcı adına manuel ve kontrolsüz emir göndermek.
- Audit log silmek.
- Risk sözleşmesi olmadan kullanıcı botunu aktif etmek.

---

# 5. Sayfa Mimarisi

## 5.1 Kullanıcı Sayfa Ağacı

```text
User App
├── Login
├── Dashboard
├── Ayarlar
├── Pozisyonlar
├── Geçmiş
├── Loglar
└── Risk Sözleşmesi
```

## 5.2 Dashboard Sayfası

Dashboard, normal kullanıcı için ana kontrol merkezidir. Kullanıcı her şeyi buradan anlamalıdır.

Dashboard panelleri:

```text
Dashboard
├── API Durumu
├── Bot Durumu
├── Bot Modu
│   ├── Kapalı
│   ├── Açık
│   └── Otomatik
├── Bot Bütçesi
├── Günlük Kâr/Zarar
├── Açık Pozisyonlar
├── Açık Emirler
├── Seçili Filtreler
├── Seçili Stratejiler
├── Karabasan Kararı
├── Bot Neden İşlem Açmadı?
├── Risk Durumu
├── Son Sinyal
├── Son Emir
├── Canlı Loglar
└── Emergency Stop
```

Dashboard’un kullanıcıya vermesi gereken en kritik cümle:

```text
Bot şu anda işlem açmıyor çünkü Karabasan WAIT durumda ve BTC trendi negatif.
```

veya:

```text
Bot işlem açabilir. API bağlı, bütçe uygun, risk limiti dolmadı, Karabasan ALLOW durumda.
```

## 5.3 Ayarlar Sayfası

Ayarlar sayfası kullanıcının kendi hesabını yönettiği yerdir.

Ayarlar panelleri:

```text
Ayarlar
├── Binance API Key
├── Binance API Secret
├── API Bağlantı Testi
├── Binance Bakiye Okuma
├── Bota Ayrılan USDT
├── Pozisyon Başına USDT
├── Maksimum Açık Pozisyon
├── Günlük Zarar Limiti
├── Stop Loss Parametresi
├── Take Profit Parametresi
├── Risk Seviyesi
├── Basit Mod / Uzman Mod
├── Risk Sözleşmesi Durumu
└── Bildirim Tercihleri
```

İlk canlı sürümde kullanıcıya çok fazla profesyonel parametre açılmamalıdır. Bazı parametreler sadece okunabilir gösterilir. Örnek:

- Günlük zarar limiti: sistem tarafından belirlenir, kullanıcı görür.
- Stop loss mantığı: sistem tarafından belirlenir, kullanıcı görür.
- Max açık pozisyon: paket ve risk seviyesine bağlıdır.

## 5.4 Pozisyonlar Sayfası

Pozisyonlar sayfası, açık işlemleri takip etmek içindir.

Görünecek alanlar:

- Coin.
- Giriş fiyatı.
- Güncel fiyat.
- Miktar.
- Stop Loss.
- Take Profit.
- Gerçekleşmemiş PnL.
- Açılış zamanı.
- Karabasan durumu.
- Risk açıklaması.

## 5.5 Geçmiş Sayfası

Kapanmış işlemler burada listelenir.

Görünecek alanlar:

- Coin.
- Alış zamanı.
- Satış zamanı.
- Alış fiyatı.
- Satış fiyatı.
- Miktar.
- Komisyon.
- Slippage.
- Net PnL.
- Hangi stratejiyle açıldı.
- Hangi filtrelerden geçti.
- Karabasan skoru.
- İşlem kapama nedeni.

CSV export zorunludur. Kullanıcı vergi raporu için veriyi indirebilmelidir.

## 5.6 Admin Sayfa Ağacı

```text
Admin App
├── Admin Dashboard
├── User Management
├── Package Management
├── Paper Lab
├── Karabasan Studio
├── Strategy Factory
├── Filter Factory
├── Model Registry
├── Risk Monitoring
├── Security Console
├── Incident Center
└── Emergency Control
```

## 5.7 Paper Lab Sayfası

Paper Lab sadece admin içindir.

Paper Lab amacı:

- Filtre ve strateji kombinasyonlarını test etmek.
- Her kombinasyona sanal bütçe tanımlamak.
- Gerçek piyasayı etkilemeden model performansını ölçmek.
- Risk/getiri sıralaması yapmak.
- Canlıya aday modelleri belirlemek.

Örnek kombinasyon:

```text
3 filtre x 3 strateji = 9 model
Her model = 1000 USDT sanal bütçe
İşlem modeli = 100 USDT x 10 işlem veya 200 USDT x 5 işlem
```

Paper Lab metrikleri:

- Net PnL.
- Win rate.
- Profit factor.
- Max drawdown.
- Ortalama kazanç.
- Ortalama kayıp.
- Slippage etkisi.
- Komisyon sonrası net sonuç.
- Karabasan uyumu.

## 5.8 Karabasan Studio

Karabasan Studio, admin’in piyasa karar motorunu izlediği yerdir.

Karabasan V0 girdileri:

- BTC trend.
- BTC 15 dakika ani düşüş.
- BTC volatilite.
- Binance API sağlığı.
- Sistem sağlığı.

Karabasan çıktıları:

- ALLOW.
- WAIT.
- BLOCK.

V1 ve sonrası için eklenecekler:

- BTC dominance.
- TOTAL/TOTAL2.
- Haber sentiment.
- DXY.
- Altın.
- Nasdaq.
- Open interest.
- Funding rate.
- On-chain liquidity.

---

# 6. Backend Mimarisi

Backend domain bazlı olmalıdır. Her modülün tek sorumluluğu vardır.

```text
backend/
├── main.py
├── auth/
├── users/
├── settings/
├── exchanges/
│   └── binance/
│       ├── common/
│       ├── spot/
│       └── futures_disabled/
├── trading/
│   ├── signal_engine.py
│   ├── order_lifecycle.py
│   ├── risk_engine.py
│   ├── position_manager.py
│   ├── pnl_engine.py
│   └── trade_journal.py
├── strategies/
├── filters/
├── karabasan/
├── paper_lab/
├── learning/
├── admin/
├── security/
├── monitoring/
└── storage/
```

## 6.1 Auth Modülü

Görevleri:

- Kullanıcı giriş çıkışı.
- Token üretimi.
- Token doğrulama.
- Rol kontrolü.
- Session timeout.
- Admin için 2FA hazırlığı.

## 6.2 User Isolation

Her API çağrısı token içindeki user_id ile çalışmalıdır. Frontend’den gelen user_id güvenilir değildir.

Kural:

```text
request.user_id = token’dan alınır
body.user_id = yok sayılır
```

## 6.3 Binance Connector

İlk sürümde sadece Spot desteklenir.

Görevleri:

- API key test etmek.
- Bakiye okumak.
- Sembol kurallarını okumak.
- Minimum notional kontrolü.
- Lot size kontrolü.
- Tick size kontrolü.
- Emir göndermek.
- Emir durumunu sorgulamak.
- Açık emirleri okumak.
- İşlem geçmişini okumak.

Withdrawal yetkili API key kesinlikle kabul edilmez.

## 6.4 Trading Engine

Trading Engine, sinyali emir haline çevirir.

Akış:

```text
Market Data
→ Filter Engine
→ Strategy Engine
→ Signal
→ Risk Engine
→ Karabasan Gate
→ Order Prepare
→ Binance Order
→ Order Lifecycle
→ Position Manager
→ PnL Engine
→ Trade Journal
```

## 6.5 Risk Engine

Risk Engine her emirden önce çalışır.

Kontroller:

- Bot açık mı?
- API bağlı mı?
- Risk sözleşmesi kabul edildi mi?
- Bütçe yeterli mi?
- Pozisyon başı tutar uygun mu?
- Günlük zarar limiti doldu mu?
- Maksimum açık pozisyon doldu mu?
- Aynı coin için açık emir var mı?
- Aynı coin için açık pozisyon var mı?
- Spread uygun mu?
- Likidite uygun mu?
- Stop Loss hesaplanabilir mi?
- Take Profit hesaplanabilir mi?
- Karabasan ALLOW mu?

Risk kararları:

```text
APPROVED
WAIT
BLOCKED
REDUCED_SIZE
EMERGENCY_STOP
MANUAL_REVIEW_REQUIRED
```

---

# 7. Emir Yaşam Döngüsü

Emir yaşam döngüsü net olmalıdır. Emir kaybolmamalı, iki kez açılmamalı, timeout sonrası kör tekrar yapılmamalıdır.

```text
SIGNAL_CREATED
SIGNAL_VALIDATED
RISK_CHECK_STARTED
RISK_APPROVED
ORDER_PREPARED
ORDER_SENT
ORDER_ACCEPTED
PARTIALLY_FILLED
FILLED
STOP_LOSS_ATTACHED
TAKE_PROFIT_ATTACHED
POSITION_MONITORING
EXIT_SIGNAL_RECEIVED
CLOSING_ORDER_SENT
CLOSED
PNL_CALCULATED
TRADE_JOURNAL_WRITTEN
RECONCILED
```

Hata durumları:

```text
ORDER_REJECTED
ORDER_TIMEOUT
PARTIAL_FILL_STALE
STOP_LOSS_FAILED
TAKE_PROFIT_FAILED
RECONCILIATION_MISMATCH
MANUAL_INTERVENTION_REQUIRED
```

Duplicate order koruması:

- Her sinyal için signal_id.
- Her emir için idempotency_key.
- User + symbol lock.
- Aynı kullanıcı + aynı coin + aktif emir varsa yeni emir yok.
- Aynı kullanıcı + aynı coin + açık pozisyon varsa yeni emir yok.

---

# 8. Spot Money Pilot Stratejisi

İlk canlı sürümde tek strateji kullanılmalıdır. Çoklu strateji ilk canlıda debug ve risk yönetimini zorlaştırır.

## 8.1 Coin Evreni

- Binance Spot USDT pariteleri.
- Top 20–30 yüksek hacimli coin.
- Yeni listelenen coin yok.
- Çok düşük hacim yok.
- Çok yüksek spread yok.
- Stablecoin-stablecoin pariteleri yok.

## 8.2 Timeframe

- Ana trend: 1H.
- Giriş sinyali: 15M.
- Likidite kontrolü: anlık order book / 5M snapshot.

## 8.3 Giriş Kuralları

- BTC trend negatif olmamalı.
- Coin 1H trendde güçlü olmalı.
- 15M momentum pozitif olmalı.
- Hacim ortalamanın üzerinde olmalı.
- Spread düşük olmalı.
- Order book derinliği yeterli olmalı.
- Fiyat güçlü direncin hemen altında olmamalı.
- Karabasan ALLOW olmalı.

## 8.4 Çıkış Kuralları

- Stop Loss zorunlu.
- Take Profit zorunlu.
- Günlük zarar limiti dolarsa yeni işlem yok.
- Karabasan BLOCK verirse yeni işlem yok.
- BTC ani düşerse risk modu.

## 8.5 Beklenen Değer

Her strateji için expectancy hesaplanmalıdır.

```text
Expected Value =
Win Rate x Ortalama Kazanç
- Loss Rate x Ortalama Kayıp
- Komisyon
- Slippage
```

Canlıya alınacak strateji pozitif beklenen değer göstermelidir.

---

# 9. Paper Lab Yönetim Metodu

Paper Lab canlıyı değiştirmez. Sadece öneri üretir.

Akış:

```text
Trade Journal
→ Paper Lab
→ Model Score
→ Admin Review
→ Risk Advisor Approval
→ Small Live Pilot
→ Limited Release
```

Model canlıya otomatik geçmez.

Model değerlendirme kriterleri:

- Net PnL.
- Max drawdown.
- Profit factor.
- Win rate.
- Trade count.
- Komisyon sonrası sonuç.
- Slippage sonrası sonuç.
- Karabasan uyumu.
- Farklı piyasa koşullarında stabilite.

---

# 10. Karabasan Yönetim Metodu

Karabasan ilk aşamada trade uzmanı değil, risk kapısıdır.

V0 görevleri:

- BTC trend negatifse WAIT.
- BTC ani düşüş varsa BLOCK.
- Binance API sağlıksızsa BLOCK.
- Sistem sağlıksızsa WAIT/BLOCK.

V1 görevleri:

- BTC dominance.
- TOTAL/TOTAL2.
- Haber sentiment.
- Funding/open interest.
- Altın/DXY/Nasdaq korelasyonu.

Karabasan parametreleri değiştirilecekse:

1. Paper Lab test eder.
2. Learning Engine önerir.
3. Admin inceler.
4. Risk danışmanı onaylar.
5. Yeni config version oluşur.
6. Canlıya kademeli alınır.

---

# 11. Veri Modeli

İlk MVP tabloları:

```text
users
roles
sessions
user_exchange_accounts
user_bot_settings
user_strategy_settings
user_filter_settings
risk_agreements
user_risk_acceptance
signals
orders
order_states
positions
trade_journal
risk_events
karabasan_scores
audit_logs
system_health
```

Paper Lab tabloları:

```text
paper_lab_runs
paper_lab_results
model_registry
model_versions
model_promotion_history
feature_store_symbol
feature_store_market
```

Futures ikinci faz tabloları:

```text
user_futures_settings
futures_orders
futures_positions
futures_risk_events
funding_fee_history
liquidation_risk_snapshots
```

---

# 12. API Mimarisi

## 12.1 Auth API

```text
POST /api/auth/login
POST /api/auth/logout
GET  /api/auth/me
```

## 12.2 Settings API

```text
GET    /api/settings
PUT    /api/settings/bot
PUT    /api/settings/binance
POST   /api/settings/binance/test
DELETE /api/settings/binance
```

## 12.3 Dashboard API

```text
GET /api/dashboard
GET /api/dashboard/summary
GET /api/dashboard/explanation
PUT /api/dashboard/bot-mode
PUT /api/dashboard/filters
PUT /api/dashboard/strategies
```

## 12.4 Trading API

```text
GET  /api/spot/status
GET  /api/spot/account
GET  /api/spot/orders
GET  /api/spot/positions
GET  /api/spot/pnl
POST /api/spot/emergency-stop
```

## 12.5 Admin API

```text
GET  /api/admin/users
PUT  /api/admin/users/{id}
GET  /api/admin/paper-lab
POST /api/admin/paper-lab/run
GET  /api/admin/karabasan
PUT  /api/admin/karabasan/config
POST /api/admin/emergency-stop
```

---

# 13. Güvenlik Mimarisi

Zorunlu güvenlik kararları:

- API secret düz metin saklanmaz.
- API secret frontend’e dönmez.
- Admin secret göremez.
- Withdrawal permission olan key reddedilir.
- Kullanıcı verileri tenant bazlı izole edilir.
- Audit log silinemez mantıkta tutulur.
- Her kritik işlem audit edilir.
- Admin işlemleri ayrıca işaretlenir.
- Rate limit uygulanır.
- Webhook imzasız çalışmaz.
- Emergency Stop her zaman çalışır.

---

# 14. Operasyon ve Yönetim

## 14.1 Monitoring

İzlenecek metrikler:

- API latency.
- Binance latency.
- Order latency.
- Failed orders.
- Rejected trades.
- Active bots.
- PnL.
- Win rate.
- Profit factor.
- Drawdown.
- Slippage.
- CPU/RAM.
- DB health.

## 14.2 Incident Runbook

Olay akışı:

1. Olay tespit edilir.
2. Severity belirlenir.
3. Yeni emirler durdurulur.
4. Açık emirler kontrol edilir.
5. Açık pozisyonlar kontrol edilir.
6. Reconciliation çalışır.
7. Kullanıcı etkisi belirlenir.
8. Admin raporu oluşturulur.
9. Root cause yazılır.
10. Kalıcı aksiyon kapatılır.

## 14.3 Backup

- Günlük database backup.
- Deploy öncesi backup.
- Secret backup politikası.
- Restore testi.
- Rollback prosedürü.

---

# 15. Geliştirme Sırası

Kesin sıra:

```text
1. Repo temizliği
2. PostgreSQL migration
3. Auth/RBAC
4. Secret encryption
5. User settings
6. Dashboard MVP
7. Binance Spot connector
8. Risk Engine
9. Strategy/Filter Engine
10. Order Lifecycle
11. Trade Journal
12. Audit Log
13. Karabasan V0
14. Monitoring
15. Paper Lab basic
16. Controlled Live Pilot
17. Multi-user productization
18. Karabasan V1
19. Futures testnet
20. Futures pilot
```

---

# 16. Kabul Kriterleri

Spot MVP tamamlandı sayılması için:

- Kullanıcı login olabilir.
- Kullanıcı API key ekleyebilir.
- API secret encrypted saklanır.
- Binance API test çalışır.
- Kullanıcı bot bütçesi belirleyebilir.
- Dashboard bot durumunu gösterir.
- Bot açık/kapalı mod değiştirebilir.
- Strategy Engine sinyal üretir.
- Risk Engine işlem öncesi karar verir.
- Karabasan ALLOW/WAIT/BLOCK üretir.
- Emir yaşam döngüsü kayıt altındadır.
- Açık pozisyonlar görünür.
- İşlem geçmişi görünür.
- Audit log oluşur.
- Emergency Stop çalışır.
- Controlled Live Pilot düşük bütçeyle başlatılabilir.

---

# 17. Sonuç

Bu README HMTSTC’nin ana mimari dokümanıdır. Kurulum ve geliştirme adımları `todo.md` dosyasında verilmiştir. Geliştirici ekip önce `todo.md` dosyasındaki sıralı adımları uygulamalı, ardından bu README’deki kabul kriterleriyle işi kontrol etmelidir.

## Paket 10.23 Dashboard

Dashboard bot kontrollerini, cached CoinFilter ozetini, portfoy durumunu ve canvas tabanli Live Trade Network gorunumunu tek terminal ekranda birlestirir. Dashboard render'i agir scan baslatmaz ve backend engine davranisini degistirmez. Kalite kapisi `scripts/level1_40_37_dashboard_live_trade_network_audit.py` dosyasidir.

## Paket 10.21.5 Revize 3 Runtime Contract

Bot start ve stop komutlari heartbeat-only runtime sozlesmesi kullanir. Otomatik start/status/dashboard scan flagleri ve background scan worker varsayilan olarak kapalidir. Start thread veya process baslatmaz; status ve dashboard cached state okur. Kalite kapisi `scripts/level1_40_36_5_rev3_start_stop_runtime_contract_audit.py` dosyasidir.
