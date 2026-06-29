window.HMTSTC_PAGES = window.HMTSTC_PAGES || {};

(function () {
  function esc(value) {
    return HMTSTC_APP.escapeHtml(value === undefined || value === null ? "" : value);
  }

  function data() {
    return window.HMTSTC_DATA || {};
  }

  function number(value, fallback) {
    const parsed = Number(value);
    return Number.isFinite(parsed) ? parsed : (fallback || 0);
  }

  function money(value) {
    return number(value, 0).toLocaleString("tr-TR", { minimumFractionDigits: 2, maximumFractionDigits: 2 }) + " USDT";
  }

  function time(value) {
    return value ? String(value).replace("T", " ").slice(0, 19) : "-";
  }

  function join(items, fallback) {
    return Array.isArray(items) && items.length ? items.slice(0, 5).join(" | ") : (fallback || "-");
  }

  function actionFor(definition, current) {
    const label = String(definition || "").toLowerCase();
    const status = String(current === undefined || current === null ? "" : current).trim().toLowerCase();
    const empty = !status || status === "-";

    if (empty) return "Veri yok; backend sync veya ilgili endpoint kontrol edilmeli.";
    if (["review", "warning", "warn", "watch", "pending", "manual", "manuel kontrol"].indexOf(status) !== -1) {
      return "Admin kontrolü gerekli; kanıt netleşmeden canlı adıma geçme.";
    }
    if (["blocked", "block", "error", "fail", "failed", "danger", "critical", "bloke"].indexOf(status) !== -1) {
      return "Blokajı çöz; bu satır düzelmeden canlı işlem açma.";
    }
    if (label.indexOf("mikro canlı") !== -1 && status === "blocked") {
      return "Owner onayı, token ve limit kapılarını tamamla.";
    }
    if (label.indexOf("güvenlik") !== -1 && status === "locked") {
      return "Aksiyon yok; gerçek işlem kapıları kilitli kalmalı.";
    }
    if (["ok", "ready", "healthy", "passed", "clear", "locked", "reconciled", "pass", "hazır"].indexOf(status) !== -1) {
      return "Aksiyon yok; izlemeye devam et.";
    }
    if (status.indexOf("aktif") !== -1 || status === "active" || status === "running") {
      return "Bot ve risk limitlerinin kullanıcı tercihiyle uyumunu izle.";
    }
    if (status.indexOf("pasif") !== -1 || status === "off" || status === "disabled" || status === "closed") {
      return "Kullanıcı başlatmadıysa aksiyon yok; beklenen durum buysa normal.";
    }
    if (label.indexOf("final karar") !== -1) {
      return status === "watch" ? "Aksiyon yok; sistem izleme modunda." : "Kararı dashboard/Jarvis aksiyonuyla karşılaştır.";
    }
    if (label.indexOf("son tick") !== -1 || label.indexOf("son sync") !== -1) {
      return current === "-" ? "Veri gelmiyor; servis veya sync akışını kontrol et." : "Zaman eskiyse servis döngüsünü kontrol et.";
    }
    return "Değeri beklenen durumla karşılaştır; sapma varsa admin kontrolü yap.";
  }

  function row(definition, current, expected, importance, action) {
    return "<tr>" +
      "<td><b>" + esc(definition) + "</b></td>" +
      "<td>" + esc(current) + "</td>" +
      "<td>" + esc(expected) + "</td>" +
      "<td>" + esc(importance) + "</td>" +
      "<td><b>" + esc(action || actionFor(definition, current)) + "</b></td>" +
    "</tr>";
  }

  function section(title) {
    return '<tr class="admin-table-section"><td colspan="5">' + esc(title) + '</td></tr>';
  }

  window.HMTSTC_PAGES.admin = function () {
    const d = data();
    const dashboard = d.dashboard || {};
    const summary = d.summary || {};
    const bot = d.botStatus || {};
    const reports = d.reports || {};
    const risk = dashboard.risk || ((d.settings || {}).risk || {});
    const settings = d.settings || {};
    const botSettings = settings.bot || {};
    const scan = d.botScan || {};
    const observability = d.observabilitySummary || {};
    const latency = d.observabilityLatency || observability.latency || {};
    const errors = d.observabilityEndpointErrors || observability.endpoint_errors || {};
    const stale = d.observabilityStale || observability.stale_data || {};
    const regime = d.revision31MarketRegime || d.marketRegimeFinal51 || {};
    const orderbook = d.revision31Orderbook || {};
    const noTrade = d.revision31NoTrade || d.noTradeFinal || {};
    const allocation = (d.portfolioAllocationFinal || {}).allocation_final || d.revision32Allocation || {};
    const reserve = (d.usdtReservePolicy || {}).reserve_policy || d.revision32Reserve || allocation.reserve_policy || {};
    const cluster = (d.clusterExposure || {}).cluster_exposure || d.revision32Cluster || allocation.cluster_exposure || {};
    const approval = d.realApproval || {};
    const recommendation = approval.recommendation || reports.recommendation || {};
    const safety = approval.safety || reports.real_trade_safety || {};
    const production = d.productionEnvironment || d.productionReadiness || {};
    const binance = d.binanceReadonly || d.binanceReadOnly || {};
    const onboarding = d.onboarding || {};
    const paper = reports.paper_lab || d.paperLab || {};
    const realReadiness = d.realReadiness || {};
    const rules = d.rules || {};
    const filters = Array.isArray(rules.filters) ? rules.filters : [];
    const strategies = Array.isArray(rules.strategies) ? rules.strategies : [];
    const activeFilters = Array.isArray(rules.selected_filter_ids) ? rules.selected_filter_ids : [];
    const activeStrategies = Array.isArray(rules.selected_strategy_ids) ? rules.selected_strategy_ids : [];
    const positions = Array.isArray(d.positions) ? d.positions : [];
    const history = Array.isArray(d.history) ? d.history : [];
    const finalDecision = summary.final_decision || summary.decision || dashboard.final_decision || recommendation.action || "WATCH";

    const rows = [
      section("Gizlenen Hazırlık ve Güvenlik Sayfaları"),
      row("Üretim ortamı", production.status || "review", "Backend, frontend, nginx, izinler ve deploy kanıtı hazır olmalı.", "Canlı ortamın yanlış servis, proxy veya dosya izniyle çalışmasını engeller."),
      row("Binance salt okuma", binance.status || "ready", "API bağlantısı secret göstermeden ve emir göndermeden doğrulanmalı.", "Trade yetkisi driftini ve yanlışlıkla gerçek emir riskini kontrol eder."),
      row("Kullanıcı kurulumu", onboarding.status || "review", "Tek kullanıcı, API maskeleme, risk profili ve sembol izinleri tamamlanmalı.", "Kiralayan kullanıcının yanlış riskle veya eksik profil ile başlamasını önler."),
      row("Paper trading", paper.status || "ready", "Scanner, filtre, strateji, execution ve journal zinciri gerçek para olmadan çalışmalı.", "Model ve kural seçiminin gerçek emirden önce kanıtlanmasını sağlar."),
      row("Mikro canlı izinleri", realReadiness.status || "blocked", "Max notional, max loss, owner approval ve activation token kapıları kapalı/açılabilir olmalı.", "Canlı denemeye geçişi sınırlı ve izlenebilir hale getirir.", "Blocked ise normal güvenlik kilidi olabilir; canlı deneme istiyorsan owner onayı, token ve limitleri tamamla."),
      row("Güvenlik merkezi", safety.status || "locked", "Real submit, real close, emergency close ve auto apply varsayılan kapalı kalmalı.", "Ana güvenlik kontratlarını izler; kullanıcı ekranında kafa karışıklığı yaratmadan admin’e taşır.", "Locked iyi durumdur; sadece kontrollü canlı denemede owner onayıyla aç."),
      row("Kalite kapıları", reports.quality_status || d.qualityStatus || "review", "Frontend, sync ve Rev985-Rev1015 kalite komutları geçmeli.", "Deploy veya canlı deneme öncesi test zincirinin kırılmadığını kontrol eder."),
      row("Kullanıcı akışı", "Admin denetiminde", "Günlük kullanım Jarvis/Dashboard; hazırlık ve kanıtlar Admin tablosunda kalmalı.", "Kullanıcının operasyon sırasını sadeleştirir, debug sayfalarını menüden temizler.", "Aksiyon yok; kullanıcıya bu tabloyu açma, admin denetiminde tut."),

      section("Mevcut Admin Operasyon Verileri"),
      row("Final karar", finalDecision, "WATCH, START_READY, MANUEL KONTROL veya BLOKE net görünmeli.", "Sistemin bugün ne yapması gerektiğini kontrol eder.", String(finalDecision).toUpperCase() === "WATCH" ? "Aksiyon yok; sistem izleme modunda." : "Karar canlı aksiyon öneriyorsa risk ve safety satırlarıyla birlikte onayla."),
      row("Sistem durumu", summary.status || dashboard.status || "review", "Healthy/ready değilse admin incelemesi gerekir.", "Genel veri ve karar katmanı sağlığını gösterir."),
      row("Bot çalışma durumu", bot.bot_running ? "Aktif" : "Pasif", "Kiralayan kullanıcı botu Jarvis/Dashboard üzerinden yönetmeli.", "Admin için runtime ve kullanıcı seçiminin tutarlı olup olmadığını kontrol eder."),
      row("Bot kontrol modu", botSettings.control_mode || (bot.bot_running ? "open" : "closed"), "closed/open/automatic değerlerinden biri olmalı.", "Otomatik modun yanlışlıkla açık kalmasını veya pasif görünümü bozulmasını önler."),
      row("Son tick", time(bot.last_tick || dashboard.last_tick), "Yakın zamanda güncellenmiş olmalı.", "Bot döngüsünün durup durmadığını kontrol eder."),
      row("Son sync", (HMTSTC_APP.state || {}).lastSyncAt || "-", "Kullanıcı ekranı eski veriyle kalmamalı.", "Frontend verisinin backend durumuyla taze kalmasını kontrol eder."),

      section("Finans, Risk ve Karar Katmanı"),
      row("Wallet", money(dashboard.wallet_value), "Paper/izleme değeri tutarlı olmalı.", "Kullanıcıya görünen portföy değerinin kaynağını kontrol eder."),
      row("Daily PnL", money(dashboard.daily_pnl), "Günlük limit ile birlikte okunmalı.", "Günlük zarar veya sapma riskini erken gösterir."),
      row("Total PnL", money(dashboard.total_pnl), "Journal ve paper sonuçlarıyla tutarlı olmalı.", "Performans metriklerinin yanıltıcı olmamasını kontrol eder."),
      row("Açık pozisyon", positions.length + " / " + (risk.max_open_positions || botSettings.max_open_positions || "-"), "Limit aşılmamalı.", "Risk slotlarının dolup dolmadığını kontrol eder."),
      row("İşlem başı USDT", money(bot.usdt_per_position || botSettings.usdt_per_position), "Kullanıcının risk profiline uygun olmalı.", "Tek işlem büyüklüğü riskini kontrol eder."),
      row("Win rate", number(dashboard.win_rate, 0).toFixed(2) + "%", "Tek başına karar değildir; trade sayısıyla okunmalı.", "Yanlış iyimser performans algısını engeller."),
      row("Profit factor", number(dashboard.profit_factor, 0).toFixed(2), "Expectancy ve drawdown ile birlikte değerlendirilmeli.", "Model kalitesini kaba PnL dışında ölçer."),
      row("Scan", (scan.candidates_count || dashboard.candidates_count || 0) + " aday / " + (scan.scanned || dashboard.scanned || 0) + " taranan", "Taranan evren ve aday sayısı tutarlı olmalı.", "Karar yoksa sebebin piyasa mı filtre mi olduğunu gösterir."),
      row("En sık eleme", scan.top_rejection_reason || dashboard.top_rejection_reason || "-", "No-trade nedeni anlaşılır olmalı.", "Kullanıcıya işlem yok durumunu açıklamak için önemlidir."),
      row("Öneri güveni", (recommendation.action || "WATCH") + " / " + (recommendation.confidence || "low"), "Düşük güven canlı karara dönüşmemeli.", "Model önerisinin admin onayı gerektirip gerektirmediğini gösterir."),

      section("Model, Kural ve Observability"),
      row("Paper model sayısı", paper.models_count || 0, "Yeterli model ve örneklem oluşmalı.", "Strateji seçiminin veriyle desteklenip desteklenmediğini kontrol eder."),
      row("Aktif real model", (reports.real_model || {}).active_real_model_id || "-", "Owner onayı olmadan otomatik değişmemeli.", "Gerçek modele geçişin kontrolsüz olmasını engeller."),
      row("Filtre/strateji sayısı", filters.length + " filtre / " + strategies.length + " strateji", "Kural seti boş veya aşırı geniş olmamalı.", "Jarvis’te seçilen çalışma alanının kalitesini kontrol eder."),
      row("Seçili filtre/strateji", (activeFilters.length || "hepsi") + " / " + (activeStrategies.length || "hepsi"), "Kullanıcı seçimi paper lab ile uyumlu olmalı.", "Yanlış kombinasyonla bot çalıştırmayı engeller."),
      row("Health score", (observability.score !== undefined ? observability.score : "-") + " / 100", "Düşük skorda canlı adım durmalı.", "Endpoint, latency ve veri tazeliğini tek skorla izler."),
      row("Endpoint error", (errors.error_rate_pct !== undefined ? errors.error_rate_pct : 0) + "%", "Yüksek hata oranı blokaj sebebi olmalı.", "API güvenilirliğini kontrol eder."),
      row("Binance latency", (latency.binance_latency_ms || 0) + " ms", "Gecikme limit dışında olmamalı.", "Read-only ve karar verisinin zamanında geldiğini kontrol eder."),
      row("Stale data", stale.status || "-", "Stale veriyle karar verilmemeli.", "Eski veriyle bot/karar ekranı üretmeyi engeller."),

      section("Piyasa, Allocation ve Safety"),
      row("Market regime", regime.regime || "-", "Strateji rejimle uyumlu olmalı.", "Piyasa koşuluna ters model çalışmasını önler."),
      row("No-trade", noTrade.no_trade_active ? "ACTIVE" : "clear", "No-trade aktifse bot işlem üretmemeli.", "Volatilite/likidite/sinyal yok durumlarında sistemi durdurur.", noTrade.no_trade_active ? "Aksiyon yok; no-trade kalkana kadar işlem açma." : "Aksiyon yok; no-trade kilidi temiz."),
      row("Orderbook kontrolü", (orderbook.confirmed_count || 0) + " / " + (orderbook.sample_size || 0), "Yeterli onay yoksa canlı adım açılmamalı.", "Likidite ve spread kaynaklı execution riskini kontrol eder."),
      row("USDT reserve", (reserve.target_reserve_percent || 0) + "%", "Rezerv korunmalı, deployable USDT limitli kalmalı.", "Portföyün tamamının riske atılmasını engeller."),
      row("Deployable USDT", money(allocation.deployable_usdt || reserve.deployable_usdt || 0), "Aktif trade bütçesi güvenlik limitleriyle sınırlı olmalı.", "Allocation kararının riski aşmadığını gösterir."),
      row("Cluster risk", ((cluster.clusters || []).filter(function (item) { return item.status !== "ok"; })).length + " uyarı", "Aynı korelasyon kümesine aşırı yüklenilmemeli.", "Benzer coinlerde toplu zarar riskini kontrol eder."),
      row("Safety blocker", join(safety.blockers, "-"), "Blocker varsa gerçek adım kilitli kalmalı.", "Admin’in canlı risk sebebini hızlı görmesini sağlar."),
      row("İşlem geçmişi", (dashboard.total_trades || history.length || 0) + " kayıt", "Journal eksiksiz olmalı.", "Performans ve kanıt zincirinin kaybolmadığını kontrol eder.")
    ];

    return '<div class="admin-table-page">' +
      '<div class="admin-table-title">' +
        '<span>Admin</span>' +
        '<h2>Operasyon ve Denetim Tablosu</h2>' +
        '<p>Kullanıcı menüsünden kaldırılan hazırlık, güvenlik, kalite ve debug verileri burada tek tabloda tutulur.</p>' +
      '</div>' +
      '<div class="admin-table-wrap">' +
        '<table class="admin-control-table">' +
          '<thead><tr><th>Tanım</th><th>Mevcut durum</th><th>Olması gereken durum</th><th>Neyi kontrol eder, neden önemli?</th><th>Aksiyon</th></tr></thead>' +
          '<tbody>' + rows.join("") + '</tbody>' +
        '</table>' +
      '</div>' +
    '</div>';
  };
}());
