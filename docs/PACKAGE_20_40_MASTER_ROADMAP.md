# HMTSTC Paket 20-40 Master Roadmap

**Kaynak:** hmtstc10.zip
**Oluşturma zamanı:** 2026-06-14T22:46:19Z

Bu dosya Paket 20-40 arasında yapılacak işleri unutulmaması için ana yazılı kaynak olarak tutulur.

## Çalışma sistematiği

1. Paketler sırayla uygulanır.
2. Bir paket lokal audit geçmeden commit/push yapılmaz.
3. Bir paket VPS kabulü geçmeden sonraki pakete geçilmez.
4. CoinFilter tamamlanmadan strateji/karabasan/live emir tarafına geçilmez.
5. Dashboard tasarımı bozulmaz; sadece veri contractı düzeltilir.
6. Runtime/store/env dosyaları asla commitlenmez.

## Paket listesi

### Paket 20 — Baseline Freeze + Blackbox Damage Control

**Amaç:** Mevcut hmtstc10 kodunu güvenli baseline haline getirmek; Blackbox kaynaklı karışık/eksik değişiklikleri ayıklamak.

**Ana adımlar:**
1. `git status -sb`, `git log --oneline -5`, HEAD dosya listesi ve runtime dosya sızıntısı kontrol edilecek.
2. `3bd86ec` değişiklikleri `d4f06c7` ile diff edilecek; Blackbox'ın eksik bıraktığı 5.4 script/doküman varsa güvenilir kabul edilmeyecek.
3. Runtime/store/env dosyaları için `.gitignore` ve staged diff güvenliği tekrar doğrulanacak.
4. Paket 20 audit scripti repo temizliği, syntax ve mevcut 39.x auditlerini tek komutta doğrulayacak.

Detay: `Paketler/paket20.md`

### Paket 21 — CoinFilter Final UI Simplification

**Amaç:** CoinFilter sayfasını hedef formata sadeleştirmek; Sistem Sabit Korumaları ve gereksiz teknik satırları kaldırmak.

**Ana adımlar:**
1. CoinFilter UI'da `Sistem Sabit Korumaları` bölümünden itibaren kullanıcıyı yoran guard/diagnostic kartları kaldırılacak.
2. `RSI Periyodu`, `Volatilite Timeframe`, `Volatilite Mum Sayısı` ana kullanıcı girdisi olmaktan çıkarılacak.
3. Kalan parametreler: hacim, işlem sayısı, volatilite, max spread, hacim artışı, RSI min/max, EMA/MACD, skor, hariç coinler, scan limitleri.
4. Kaydet/Test Scan/Son Scan Yenile butonları sade parametre bloğunun üst/alt bölümünde korunacak.

Detay: `Paketler/paket21.md`

### Paket 22 — CoinFilter Settings Contract

**Amaç:** CoinFilter ayarlarının tek kaynak, null olmayan ve scan tarafından kullanılan contractını kesinleştirmek.

**Ana adımlar:**
1. Settings tek kaynak: settings_store; shadow_store sadece runtime mirror olacak.
2. `users.<u>.settings.coin_filter` null dönmeyecek.
3. Kaydet sadece settings kaydedecek; scan başlatmayacak.
4. `last_scan.settings_snapshot` ve `last_scan.coin_filter_settings_used` her scan sonrası yazılacak.

Detay: `Paketler/paket22.md`

### Paket 23 — Sequential Unique CoinFilter Pipeline

**Amaç:** CoinFilter eleme sayımlarını unique ve sıralı pipeline mantığına geçirmek.

**Ana adımlar:**
1. Filtre sırası sabitlenecek: hacim→işlem sayısı→volatilite→spread→hacim artışı→RSI→EMA→MACD→skor→excluded.
2. Her coin ilk başarısız filtrede unique elenecek; `filter_rejection_counts` unique sayım olacak.
3. Kümülatif ek sebepler gerekiyorsa ayrı `filter_rejection_counts_cumulative` alanına yazılacak.
4. UI satır sayıları ana unique `filter_rejection_counts` alanından beslenecek.

Detay: `Paketler/paket23.md`

### Paket 24 — Binance Market Truth Layer

**Amaç:** Fiyat, quote volume, trade count, spread ve sembol evrenini gerçek Binance public verisiyle güvenilir okumak.

**Ana adımlar:**
1. Binance 24h ticker kaynak alanları normalize edilecek: `quoteVolume`, `count`, `lastPrice`, `weightedAvgPrice`, high/low.
2. USDT volume ve trade count gerçek Binance alanından okunacak; UI'da başka hacim gösterilmeyecek.
3. Sembol evreninde stable/leveraged/invalid guard backend içinde kalacak; kullanıcı UI'da karışıklık görmeyecek.
4. Market cache ve timeout sınırları CPU-safe kalacak.

Detay: `Paketler/paket24.md`

### Paket 25 — Real Technical Filter Binding

**Amaç:** RSI/EMA/MACD/volume growth filtrelerini gerçek veriyle ve CPU-safe şekilde bağlamak.

**Ana adımlar:**
1. RSI 15m/1h/4h gerçek kline datasıyla hesaplanacak; proxy 50 gerçek filtre kararı sayılmayacak.
2. EMA/MACD gerçek deep analiz içinde çalışacak; hafif scan sadece aday prefilter olacak.
3. `volume_growth_multiplier` previous volume average hesaplayamıyorsa sessiz geçirmeyecek; source yazacak.
4. Deep analiz en iyi adaylarda limitli ve deadline/cancel destekli çalışacak.

Detay: `Paketler/paket25.md`

### Paket 26 — Candidate Handoff to Strategies

**Amaç:** CoinFilter'dan geçen adayların strateji motoruna tek ve temiz contract ile aktarılmasını sağlamak.

**Ana adımlar:**
1. CoinFilter output contract: `scan_id`, `time`, `settings_used`, `candidates`, `scan_rows`, `passed`, `first_rejection_reason`.
2. Strateji motoru sadece `passed === true` adayları alacak.
3. Dashboard network sadece candidate handoff listesini gösterecek.
4. Rejected coinler stratejiye girmeyecek.

Detay: `Paketler/paket26.md`

### Paket 27 — Strategy Engine Runtime Contract

**Amaç:** Stratejilerin sadece aday coinlerde çalışmasını, çıktılarını ve toggles/persistence mantığını netleştirmek.

**Ana adımlar:**
1. Strateji toggles, active strategy listesi ve strategy output schema netleşecek.
2. Strateji sonuçları: `strategy_id`, `symbol`, `signal`, `confidence`, `entry_reason`, `invalid_reasons`.
3. Paper Lab ile canlı strategy execution ayrımı korunacak.
4. Strateji yoksa bot işlem açmayacak; sebep loglanacak.

Detay: `Paketler/paket27.md`

### Paket 28 — Karabasan Risk Final Gate

**Amaç:** Strateji sinyalinden sonra Karabasan/risk gate ile işlem iznini kesinleştirmek.

**Ana adımlar:**
1. Karabasan score ve hard block listesi strategy output üzerine uygulanacak.
2. API yok, bot kapalı, risk limit, likidite/spread, aynı coin pozisyon, zarar limiti hard block olacak.
3. Karabasan sonucu `approved`, `score`, `blocks`, `warnings` şeklinde yazılacak.
4. User dashboard kısa karar açıklaması görecek; owner detay görecek.

Detay: `Paketler/paket28.md`

### Paket 29 — Bot Runtime Truth + Safe Loop

**Amaç:** Bot açık/kapalı/otomatik durumunu gerçek loop/worker/heartbeat ile uyumlu hale getirmek.

**Ana adımlar:**
1. Bot açık görünüyorsa gerçek loop/worker/heartbeat de doğrulanacak.
2. Start/stop/emergency stop thread/worker state ile uyumlu olacak.
3. Otomatik mod market confidence düşükse işlem açmayacak.
4. Bot loop CPU spike üretmeyecek; her tick timeout/cancel ile bitecek.

Detay: `Paketler/paket29.md`

### Paket 30 — Paper/Dry Execution Rehearsal

**Amaç:** Canlı emir göndermeden önce order preview ve dry-run ile tüm işlem akışını test etmek.

**Ana adımlar:**
1. Order preview gerçek emirden önce oluşturulacak.
2. Dry-run execution ledger ile tüm karar akışı kanıtlanacak.
3. Minimum miktar, stepSize, minNotional, fee tahmini yapılacak.
4. Canlı emir kapalıyken sistem işlem açmış gibi göstermeyecek.

Detay: `Paketler/paket30.md`

### Paket 31 — Binance Spot Micro Live Adapter

**Amaç:** Küçük tutarlı kontrollü gerçek spot emir adaptörünü risk limitiyle devreye almak.

**Ana adımlar:**
1. Spot micro live emir adaptörü sadece owner izinli ve düşük miktarla çalışacak.
2. Binance order submit response, clientOrderId ve error mapping kaydedilecek.
3. Retry kontrollü olacak; duplicate submit engellenecek.
4. Micro live pilot için kill switch zorunlu olacak.

Detay: `Paketler/paket31.md`

### Paket 32 — Position Lifecycle + Exit Manager

**Amaç:** Açık pozisyon, TP/SL, duplicate position guard ve kapanış lifecycle'ını kurmak.

**Ana adımlar:**
1. Açık pozisyon store contractı düzenlenecek.
2. TP/SL, manuel close, emergency close ve stale position reconciliation yapılacak.
3. Aynı symbol duplicate position engellenecek.
4. Order status poller ve Binance balance reconciliation eklenecek.

Detay: `Paketler/paket32.md`

### Paket 33 — Final Rental User Dashboard

**Amaç:** Kiralanan kullanıcı için tek Summary/Dashboard ekranını ürün haline getirmek.

**Ana adımlar:**
1. Dashboard bot kontrolleri header dışına tek ekranda alınacak.
2. API status, bot state, scan summary, candidates, logs, PnL, package/risk readiness tek sayfada olacak.
3. Mobilde start/stop/emergency görünür kalacak.
4. Retro/network animasyon yalnızca geçen adaylardan beslenecek.

Detay: `Paketler/paket33.md`

### Paket 34 — Owner/Admin Operations

**Amaç:** Kullanıcı, paket, kira günü, komisyon ve admin operasyonlarını netleştirmek.

**Ana adımlar:**
1. Owner kullanıcı ekleme, kira günü, paket, API durumu, komisyon ayarlarını yönetecek.
2. Kullanıcı owner komisyon gelir detayını görmeyecek.
3. Süre dolunca kullanıcı suspended/waiting mode'a geçecek.
4. Admin-only Paper Lab ve strategy/filter editor ayrımı korunacak.

Detay: `Paketler/paket34.md`

### Paket 35 — Observability + 8H Report

**Amaç:** Canlı log, audit, 8 saat rapor ve hata kanıt sistemini ürünleştirmek.

**Ana adımlar:**
1. Audit log kullanıcı aksiyonlarını ve sistem kararlarını ayrı tutacak.
2. 8 saat rapor scan, aday, sinyal, blok, işlem ve PnL özetini verecek.
3. Hatalar stack trace olarak user'a değil owner audit'e yazılacak.
4. VPS sağlık kontrolleri dashboard'a özet geçecek.

Detay: `Paketler/paket35.md`

### Paket 36 — PnL, Fee, Commission Truth

**Amaç:** Kullanıcı net PnL, Binance fee, sistem komisyonu ve owner gelirini doğru hesaplamak.

**Ana adımlar:**
1. Binance fee, sistem komisyonu ve net PnL ayrılacak.
2. User net sonucu görecek; owner commission income görecek.
3. Position close sonrası realized PnL kesinleşecek.
4. Rapor ve dashboard aynı hesaplama kaynağını kullanacak.

Detay: `Paketler/paket36.md`

### Paket 37 — CPU, Rate Limit, Timeout Hardening

**Amaç:** CPU %100, Binance timeout, rate-limit ve worker kaçaklarını kalıcı kapatmak.

**Ana adımlar:**
1. Binance timeout ve urlopen blokları deadline/cancel ile kapatılacak.
2. CPU %100 yapan scan/worker tekrar edemeyecek.
3. Rate-limit backoff ve cache uygulanacak.
4. Top thread ve endpoint log kabul testleri eklenecek.

Detay: `Paketler/paket37.md`

### Paket 38 — Deploy, Backup, Rollback

**Amaç:** VPS deploy, backup, rollback ve secret güvenliğini standartlaştırmak.

**Ana adımlar:**
1. Deploy script runtime files stage etmeyecek.
2. VPS pull/restart/test akışı standart komut dosyasına alınacak.
3. Backup ve rollback prosedürü yazılı ve denenmiş olacak.
4. Secret/API key güvenlik kontrolü auditlenəcək.

Detay: `Paketler/paket38.md`

### Paket 39 — End-to-End Live Rehearsal

**Amaç:** CoinFilter→Strateji→Karabasan→Order Preview→Micro Live akışını baştan sona kanıtlamak.

**Ana adımlar:**
1. Canlı prova: cached scan, manuel test scan, strategy signal, Karabasan reject/approve, dry order preview.
2. Micro live kapalıyken hiç emir gitmeyecek.
3. Micro live açıkken sadece izinli sembol/tutarla deneme yapılacak.
4. 24 saat gözlem için CPU/RAM/log/PnL raporu alınacak.

Detay: `Paketler/paket39.md`

### Paket 40 — Production Release Candidate

**Amaç:** Tüm auditleri ve canlı kabul kriterlerini geçirerek release candidate çıkarmak.

**Ana adımlar:**
1. Tüm Paket 20-39 auditleri tek master auditte çalışacak.
2. Final ZIP içinde runtime/store/env olmayacak.
3. VPS production checklist tamamlanacak.
4. RC tag/commit ve işletme prosedürü çıkarılacak.

Detay: `Paketler/paket40.md`
