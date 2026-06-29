window.HMTSTC_PAGES = window.HMTSTC_PAGES || {};

window.HMTSTC_COIN_FILTER_ACTIONS = window.HMTSTC_COIN_FILTER_ACTIONS || {
  toNumber: function (value, fallback) {
    let raw = String(value === undefined || value === null ? "" : value)
      .trim()
      .replace(/USDT/ig, "")
      .replace(/USD/ig, "")
      .replace(/\$/g, "")
      .replace(/%/g, "")
      .replace(/\s+/g, "")
      .toLowerCase();

    if (raw === "") return fallback;

    let multiplier = 1;
    if (raw.endsWith("k")) {
      multiplier = 1000;
      raw = raw.slice(0, -1);
    } else if (raw.endsWith("m")) {
      multiplier = 1000000;
      raw = raw.slice(0, -1);
    } else if (raw.endsWith("b")) {
      multiplier = 1000000000;
      raw = raw.slice(0, -1);
    }

    if (raw.indexOf(",") !== -1 && raw.indexOf(".") === -1) {
      const decimalPart = raw.split(",").pop();
      raw = decimalPart && decimalPart.length === 3 ? raw.replace(/,/g, "") : raw.replace(/,/g, ".");
    } else {
      raw = raw.replace(/,/g, "");
    }

    const parsed = Number(raw) * multiplier;
    return Number.isFinite(parsed) ? parsed : fallback;
  },

  normalizeExcludedSymbols: function (value) {
    const seen = {};
    const clean = [];
    String(value === undefined || value === null ? "" : value).split(",").forEach(function (item) {
      const symbol = String(item || "").trim().replace(/\s+/g, "").toUpperCase();
      if (!symbol || seen[symbol]) return;
      seen[symbol] = true;
      clean.push(symbol);
    });
    return clean.join(",");
  },

  clone: function (value) {
    try {
      return JSON.parse(JSON.stringify(value || {}));
    } catch (error) {
      return {};
    }
  },

  samePayload: function (left, right) {
    if (HMTSTC_APP.sameJsonPayload) {
      return HMTSTC_APP.sameJsonPayload(left || {}, right || {});
    }

    try {
      return JSON.stringify(left || {}) === JSON.stringify(right || {});
    } catch (error) {
      return false;
    }
  },

  initDraft: function () {
    if (HMTSTC_APP.state.coinFilterDirty && HMTSTC_APP.state.coinFilterDraft) {
      return HMTSTC_APP.state.coinFilterDraft;
    }

    HMTSTC_APP.state.coinFilterDraft = this.clone(HMTSTC_DATA.settings || {});
    HMTSTC_APP.state.coinFilterDraft.bot = Object.assign({}, HMTSTC_APP.state.coinFilterDraft.bot || {});
    HMTSTC_APP.state.coinFilterDraft.risk = Object.assign({}, HMTSTC_APP.state.coinFilterDraft.risk || {});
    HMTSTC_APP.state.coinFilterDraft.coin_filter = Object.assign({}, HMTSTC_APP.state.coinFilterDraft.coin_filter || {});
    HMTSTC_APP.state.coinFilterDraftSource = "backend_settings";
    return HMTSTC_APP.state.coinFilterDraft;
  },

  updateDraft: function (section, key, type, value) {
    const cleanSection = section === "bot" || section === "risk" ? section : "coin_filter";
    const draft = this.initDraft();

    draft[cleanSection] = Object.assign({}, draft[cleanSection] || {});
    draft[cleanSection][key] = type === "number"
      ? this.toNumber(value, draft[cleanSection][key])
      : (key === "excluded_symbols" ? this.normalizeExcludedSymbols(value) : String(value === undefined || value === null ? "" : value).trim());

    HMTSTC_APP.state.coinFilterDraft = draft;
    HMTSTC_APP.state.coinFilterDirty = true;
    HMTSTC_APP.state.coinFilterDraftSource = "local_draft";
  },

  collectSettings: function () {
    const source = this.clone(HMTSTC_APP.state.coinFilterDraft || HMTSTC_DATA.settings || {});
    source.bot = Object.assign({}, source.bot || {});
    source.risk = Object.assign({}, source.risk || {});
    source.coin_filter = Object.assign({}, source.coin_filter || {});

    document.querySelectorAll("[data-cf-section][data-cf-key]").forEach(function (input) {
      const section = input.getAttribute("data-cf-section");
      const key = input.getAttribute("data-cf-key");
      const type = input.getAttribute("data-cf-type") || "string";

      if (!section || !key) return;

      source[section] = Object.assign({}, source[section] || {});

      if (type === "number") {
        source[section][key] = HMTSTC_COIN_FILTER_ACTIONS.toNumber(input.value, source[section][key]);
      } else {
        source[section][key] = key === "excluded_symbols"
          ? HMTSTC_COIN_FILTER_ACTIONS.normalizeExcludedSymbols(input.value)
          : String(input.value === undefined || input.value === null ? "" : input.value).trim();
      }
    });

    return source;
  },

  save: async function (event) {
    if (event && event.preventDefault) {
      event.preventDefault();
    }

    if (HMTSTC_APP.state.coinFilterSaving) {
      return;
    }

    const scrollY = window.scrollY || document.documentElement.scrollTop || 0;

    try {
      if (!HMTSTC_APP.state.auth) {
        HMTSTC_APP.pushOperationLine("HATA: Oturum yok. CoinFilter ayarları kaydedilemedi.");
        return;
      }

      HMTSTC_APP.state.coinFilterSaving = true;
      HMTSTC_APP.state.coinFilterSaveStatus = "saving";
      HMTSTC_APP.state.coinFilterSaveMessage = "Kaydediliyor...";
      HMTSTC_APP.render();

      const settings = this.collectSettings();
      const payloadCoinFilter = this.clone(settings.coin_filter || {});
      const payloadMaxSpread = this.toNumber((settings.risk || {}).max_spread_percent, 0.35);
      const proof = {
        changedAt: new Date().toISOString(),
        payload: payloadCoinFilter,
        payloadMaxSpread: payloadMaxSpread,
        response: null,
        responseMaxSpread: null,
        storeEcho: null,
        refreshEcho: null,
        refreshMaxSpread: null,
        persisted: false,
        mismatchReason: ""
      };
      HMTSTC_APP.state.coinFilterSaveProof = proof;

      const result = await HMTSTC_APP.fetchJson("/api/settings", {
        method: "POST",
        requestKind: "mutation",
        preventGlobalAbort: true,
        timeoutMs: 30000,
        headers: {
          "Content-Type": "application/json",
          "Cache-Control": "no-store"
        },
        body: JSON.stringify(settings)
      });

      proof.response = this.clone(result.coin_filter || ((result.settings || {}).coin_filter) || {});
      proof.responseMaxSpread = this.toNumber((((result.settings || {}).risk || {}).max_spread_percent), null);
      proof.storeEcho = this.clone(result.store_echo || result.coin_filter || ((result.settings || {}).coin_filter) || {});

      const refreshed = await HMTSTC_APP.fetchJson("/api/settings", {
        requestKind: "core_read",
        preventGlobalAbort: true,
        timeoutMs: 20000
      });
      const savedSettings = refreshed.settings || refreshed || result.settings || settings;
      proof.refreshEcho = this.clone((savedSettings || {}).coin_filter || {});
      proof.refreshMaxSpread = this.toNumber((((savedSettings || {}).risk || {}).max_spread_percent), null);

      const responseMatches = this.samePayload(payloadCoinFilter, proof.response);
      const storeMatches = this.samePayload(payloadCoinFilter, proof.storeEcho);
      const refreshMatches = this.samePayload(payloadCoinFilter, proof.refreshEcho);
      const riskResponseMatches = proof.responseMaxSpread === payloadMaxSpread;
      const riskRefreshMatches = proof.refreshMaxSpread === payloadMaxSpread;
      proof.persisted = Boolean(result.persisted !== false && responseMatches && storeMatches && refreshMatches && riskResponseMatches && riskRefreshMatches);

      if (!responseMatches) {
        proof.mismatchReason = "backend_response_coin_filter_mismatch";
      } else if (!storeMatches) {
        proof.mismatchReason = "settings_store_echo_mismatch";
      } else if (!refreshMatches) {
        proof.mismatchReason = "settings_refresh_echo_mismatch";
      } else if (!riskResponseMatches) {
        proof.mismatchReason = "backend_response_max_spread_mismatch";
      } else if (!riskRefreshMatches) {
        proof.mismatchReason = "settings_refresh_max_spread_mismatch";
      }

      if (!proof.persisted) {
        HMTSTC_APP.state.coinFilterDirty = true;
        HMTSTC_APP.state.coinFilterDraft = settings;
        HMTSTC_APP.state.coinFilterDraftSource = "local_draft_persistence_mismatch";
        HMTSTC_APP.state.coinFilterSaveProof = proof;
        HMTSTC_APP.state.coinFilterSaveStatus = "error";
        HMTSTC_APP.state.coinFilterSaveMessage = "Kaydetme başarısız: backend doğrulaması eşleşmedi";
        HMTSTC_APP.pushOperationLine("HATA: CoinFilter kaydı doğrulanamadı; form değerleri korunuyor.");
        if (typeof alert === "function") {
          alert("CoinFilter kaydı backend/store/refresh zincirinde doğrulanamadı. Form değerleri korunuyor.");
        }
        return;
      }

      HMTSTC_DATA.settings = HMTSTC_APP.applySettingsPayload
        ? HMTSTC_APP.applySettingsPayload(savedSettings || settings, "coin_filter_save_refresh", { coinFilterExpected: payloadCoinFilter })
        : (savedSettings || settings);
      HMTSTC_APP.state.coinFilterDraft = this.clone(HMTSTC_DATA.settings || settings);
      HMTSTC_APP.state.coinFilterDirty = false;
      HMTSTC_APP.state.coinFilterDraftSource = "saved_backend";
      HMTSTC_APP.state.coinFilterLastSavedAt = new Date().toLocaleTimeString("tr-TR");
      HMTSTC_APP.state.coinFilterLastSavedSnapshot = this.clone(HMTSTC_DATA.settings || settings);
      HMTSTC_APP.state.coinFilterPersistedCoinFilter = payloadCoinFilter;
      HMTSTC_APP.state.coinFilterPersistedAt = proof.changedAt;
      HMTSTC_APP.state.coinFilterSaveProof = proof;
      HMTSTC_APP.state.coinFilterSaveStatus = "success";
      HMTSTC_APP.state.coinFilterSaveMessage = "Başarıyla kaydedildi";

      const scanLimit = ((HMTSTC_DATA.settings.bot || {}).scan_limit || (settings.bot || {}).scan_limit || 200);
      localStorage.setItem("hmtstc_spot_universe_limit", String(scanLimit));
      HMTSTC_APP.state.spotUniverseLimit = scanLimit;
      HMTSTC_APP.state.lastHeavySyncMs = 0;

      HMTSTC_APP.pushOperationLine("CoinFilter / bot scan ayarları kaydedildi.");

      if (HMTSTC_APP.syncApiData) {
        await HMTSTC_APP.syncApiData({ skipHeavySync: true, coinFilterExpected: payloadCoinFilter });
      }

      HMTSTC_APP.render();
      setTimeout(function () {
        window.scrollTo(0, scrollY);
      }, 0);
    } catch (error) {
      console.error("CoinFilter ayar kaydetme hatası:", error);
      const reason = HMTSTC_APP.apiErrorMessage ? HMTSTC_APP.apiErrorMessage(error, "CoinFilter ayarları kaydedilemedi") : "CoinFilter ayarları kaydedilemedi";
      HMTSTC_APP.state.coinFilterSaveStatus = "error";
      HMTSTC_APP.state.coinFilterSaveMessage = "Kaydetme başarısız: " + reason;
      HMTSTC_APP.pushOperationLine("HATA: CoinFilter ayarları kaydedilemedi. " + reason);
      if (typeof alert === "function") {
        alert(reason);
      }
    } finally {
      HMTSTC_APP.state.coinFilterSaving = false;
      HMTSTC_APP.render();
      setTimeout(function () {
        window.scrollTo(0, scrollY);
      }, 0);
    }
  },

  fetchLastScan: async function () {
    HMTSTC_APP.state.coinFilterScanLoading = true;
    HMTSTC_APP.render();
    try {
      const result = await HMTSTC_APP.fetchJson("/api/bot/last-scan", {
        requestKind: "heavy_read",
        timeoutMs: 12000
      });
      HMTSTC_DATA.botScan = result;
      HMTSTC_DATA.botScan.updated_at = result.time || new Date().toLocaleTimeString("tr-TR");
      HMTSTC_APP.pushOperationLine("Son CoinFilter scan verisi yenilendi.");
      HMTSTC_APP.render();
    } catch (error) {
      HMTSTC_APP.pushOperationLine("HATA: Son scan verisi yenilenemedi.");
      if (typeof alert === "function") {
        alert(HMTSTC_APP.apiErrorMessage ? HMTSTC_APP.apiErrorMessage(error, "Son scan verisi yenilenemedi") : "Son scan verisi yenilenemedi");
      }
    } finally {
      HMTSTC_APP.state.coinFilterScanLoading = false;
      HMTSTC_APP.render();
    }
  },

  runTestScan: async function () {
    if (HMTSTC_APP.state.coinFilterTestScanRunning) return;
    const limitInput = document.querySelector("[data-cf-section='bot'][data-cf-key='scan_limit']");
    const requestedLimit = HMTSTC_COIN_FILTER_ACTIONS.toNumber(limitInput ? limitInput.value : ((HMTSTC_DATA.settings || {}).bot || {}).scan_limit || 200, 200);
    const limit = Math.max(20, Math.min(Number(requestedLimit) || 200, 350));

    localStorage.setItem("hmtstc_spot_universe_limit", String(limit));
    HMTSTC_APP.state.spotUniverseLimit = limit;
    HMTSTC_APP.state.coinFilterTestScanRunning = true;
    HMTSTC_APP.pushOperationLine("Test scan çalışıyor...");
    HMTSTC_APP.render();

    try {
      const result = await HMTSTC_APP.fetchJson("/api/bot/coinfilter-test-scan?limit=" + encodeURIComponent(limit), {
        requestKind: "heavy_read",
        timeoutMs: 18000
      });
      HMTSTC_DATA.botScan = result;
      HMTSTC_DATA.botScan.updated_at = result.time || new Date().toLocaleTimeString("tr-TR");
      HMTSTC_APP.state.lastHeavySyncMs = Date.now();
      const scanInfo = (result.scan_diagnostics || {});
      const cacheText = result.cached || scanInfo.safe_scan_cached ? " (önbellek)" : "";
      const capText = scanInfo.safe_scan_applied_limit ? " / güvenli limit " + scanInfo.safe_scan_applied_limit : "";
      HMTSTC_APP.pushOperationLine("CoinFilter test scan tamamlandı" + cacheText + capText + ".");
    } catch (error) {
      const timedOut = error && (error.apiErrorType === "timeout" || error.apiErrorType === "http_504");
      const message = timedOut
        ? "Test scan zaman aşımına uğradı. Deep analiz kapalı olmalı; backend kontrol edin."
        : "CoinFilter test scan çalıştırılamadı.";
      HMTSTC_APP.pushOperationLine("HATA: " + message);
      if (typeof alert === "function") {
        alert(timedOut ? message : (HMTSTC_APP.apiErrorMessage ? HMTSTC_APP.apiErrorMessage(error, message) : message));
      }
    } finally {
      HMTSTC_APP.state.coinFilterTestScanRunning = false;
      HMTSTC_APP.render();
    }
  }
};


function normalizeCoinFilterScanPayload(payload) {
  const scan = payload && typeof payload === "object" ? payload : {};
  const diag = scan.scan_diagnostics && typeof scan.scan_diagnostics === "object" ? scan.scan_diagnostics : {};
  const counts = (scan.filter_rejection_counts && typeof scan.filter_rejection_counts === "object")
    ? scan.filter_rejection_counts
    : ((diag.filter_rejection_counts && typeof diag.filter_rejection_counts === "object") ? diag.filter_rejection_counts : {});
  const cumulativeCounts = (scan.filter_rejection_counts_cumulative && typeof scan.filter_rejection_counts_cumulative === "object")
    ? scan.filter_rejection_counts_cumulative
    : ((diag.filter_rejection_counts_cumulative && typeof diag.filter_rejection_counts_cumulative === "object") ? diag.filter_rejection_counts_cumulative : {});
  const volumeDiag = (scan.volume_rejection_diagnostics && typeof scan.volume_rejection_diagnostics === "object")
    ? scan.volume_rejection_diagnostics
    : ((diag.volume_rejection_diagnostics && typeof diag.volume_rejection_diagnostics === "object") ? diag.volume_rejection_diagnostics : {});
  const liquidityDiag = (scan.liquidity_rejection_diagnostics && typeof scan.liquidity_rejection_diagnostics === "object")
    ? scan.liquidity_rejection_diagnostics
    : ((diag.liquidity_rejection_diagnostics && typeof diag.liquidity_rejection_diagnostics === "object") ? diag.liquidity_rejection_diagnostics : {});
  return Object.assign({}, scan, {
    time: scan.time || scan.scan_time || scan.last_scan_at || scan.updated_at || null,
    scan_time: scan.scan_time || scan.time || scan.last_scan_at || null,
    last_scan_at: scan.last_scan_at || scan.time || scan.scan_time || null,
    filter_rejection_counts: counts,
    filter_rejection_counts_cumulative: cumulativeCounts,
    volume_rejection_diagnostics: volumeDiag,
    liquidity_rejection_diagnostics: liquidityDiag,
    scan_diagnostics: Object.assign({}, diag, {
      filter_rejection_counts: counts,
      filter_rejection_counts_cumulative: cumulativeCounts,
      volume_rejection_diagnostics: volumeDiag,
      liquidity_rejection_diagnostics: liquidityDiag
    })
  });
}

window.HMTSTC_PAGES.coinFilter = function () {
  const data = window.HMTSTC_DATA || {};
  const app = window.HMTSTC_APP || {};

  const settings = HMTSTC_COIN_FILTER_ACTIONS.initDraft();
  const botSettings = settings.bot || {};
  const riskSettings = settings.risk || {};
  const coinFilter = settings.coin_filter || {};
  const scan = normalizeCoinFilterScanPayload(data.botScan || {});
  const role = String((app.state || {}).role || localStorage.getItem("hmtstc_role") || "user").toLowerCase();
  const isAdmin = role === "owner" || role === "admin";

  const scanRows = Array.isArray(scan.scan_rows) ? scan.scan_rows : [];
  const candidates = Array.isArray(scan.candidates) ? scan.candidates : [];
  const hasCachedScan = Boolean(scan.time || scan.last_scan_at || scan.scan_time || scan.status === "ok" || Object.keys(scan.filter_rejection_counts || {}).length || scan.scanned || scan.candidates_count || scan.rejected_count);

  const defaults = {
    scan_limit: 1000,
    scan_deep_analysis_limit: 80,
    min_quote_volume: 1000000,
    min_trade_count: 1000,
    min_volatility: 0.4,
    max_spread_percent: 0.35,
    volatility_candle_count: 12,
    volatility_interval: "15m",
    rsi_min_15m: 50,
    rsi_max_15m: 75,
    rsi_min_1h: 50,
    rsi_max_1h: 75,
    rsi_min_4h: 50,
    rsi_max_4h: 75,
    volume_growth_multiplier: 1,
    excluded_symbols: "USDCUSDT,FDUSDUSDT,BUSDUSDT,TUSDUSDT,DAIUSDT,EURUSDT,USDPUSDT",
    stable_pair_guard: "Aktif",
    leveraged_token_guard: "Aktif",
    invalid_price_guard: "Aktif",
    ema_rule: "EMA 9 / EMA 21",
    macd_rule: "MACD 12 / 26",
    rsi_period: 14,
    quality_score_min: 45,
    lightweight_score_min: 55
  };

  function esc(value) {
    const fn = app.escapeHtml || function (v) { return String(v || ""); };
    return fn(value === undefined || value === null ? "" : value);
  }

  function fmt(value, digits) {
    const parsed = Number(value);
    if (!Number.isFinite(parsed)) return "-";
    return parsed.toLocaleString("tr-TR", {
      maximumFractionDigits: digits === undefined ? 2 : digits,
      minimumFractionDigits: 0
    });
  }

  function current(section, key, fallback) {
    const bucket = section === "bot" ? botSettings : (section === "risk" ? riskSettings : coinFilter);
    const value = bucket && bucket[key];
    return value === undefined || value === null || value === "" ? fallback : value;
  }

  function reasonLabel(reason) {
    const map = {
      stable_pair: "Stable parite",
      leveraged_token: "Kaldıraçlı token",
      invalid_price: "Geçersiz fiyat",
      low_quote_volume: "Düşük USDT hacim",
      low_trade_count: "Düşük işlem adedi",
      low_volatility: "Düşük volatilite",
      weak_volume_growth: "Zayıf hacim artışı",
      ema_not_aligned: "EMA uyumsuz",
      rsi_out_of_range: "RSI aralık dışı",
      macd_negative: "MACD negatif",
      low_quality_score: "Düşük kalite skoru",
      analysis_error: "Analiz hatası",
      technical_analysis_error: "Teknik analiz hatası",
      score_below_threshold: "Skor eşiği altı",
      not_passed: "Geçemedi"
    };

    return map[reason] || reason || "-";
  }

  function mergedRejectionBreakdown() {
    const merged = {};
    [scan.universe_rejection_breakdown || {}, scan.rejection_breakdown || {}].forEach(function (source) {
      Object.keys(source || {}).forEach(function (key) {
        merged[key] = Number(merged[key] || 0) + Number(source[key] || 0);
      });
    });
    return merged;
  }

  function rejectionCountForRow(item) {
    const directCounts = (scan.filter_rejection_counts && typeof scan.filter_rejection_counts === "object") ? scan.filter_rejection_counts : {};
    const key = String((item && item.key) || "").trim();
    if (key && Object.prototype.hasOwnProperty.call(directCounts, key)) {
      const value = Number(directCounts[key] || 0);
      return Number.isFinite(value) ? value : 0;
    }
    return 0;
  }

  function rejectionCountCell(item) {
    if (!hasCachedScan) {
      return "<span class='status-pill idle'>Scan yok</span>";
    }
    const count = rejectionCountForRow(item);
    const tone = count > 0 ? "warn" : "ok";
    return "<span class='status-pill " + tone + " cf-row-reject-count' title='Son scan içinde bu kriterden elenen coin sayısı'>" + esc(count) + "</span>";
  }

  function inputCell(section, key, type, value, placeholder) {
    const inputType = type === "number" ? "number" : "text";
    const step = key.indexOf("rsi_") === 0 || key.indexOf("min_") === 0 || key.indexOf("volume_") === 0 ? "0.01" : "1";

    if (key === "excluded_symbols") {
      return "<textarea class='cf-table-input' rows='3' " +
        "data-cf-section='" + esc(section) + "' " +
        "data-cf-key='" + esc(key) + "' " +
        "data-cf-type='" + esc(type) + "' " +
        "oninput='HMTSTC_COIN_FILTER_ACTIONS.updateDraft(this.getAttribute(\"data-cf-section\"), this.getAttribute(\"data-cf-key\"), this.getAttribute(\"data-cf-type\"), this.value)' " +
        "placeholder='" + esc(placeholder || "") + "'>" + esc(value) + "</textarea>";
    }

    return "<input class='cf-table-input' type='" + inputType + "' " +
      "data-cf-section='" + esc(section) + "' " +
      "data-cf-key='" + esc(key) + "' " +
      "data-cf-type='" + esc(type) + "' " +
      (inputType === "number" ? "step='" + esc(step) + "' " : "") +
      "value='" + esc(value) + "' " +
      "oninput='HMTSTC_COIN_FILTER_ACTIONS.updateDraft(this.getAttribute(\"data-cf-section\"), this.getAttribute(\"data-cf-key\"), this.getAttribute(\"data-cf-type\"), this.value)' " +
      "placeholder='" + esc(placeholder || "") + "'>";
  }

  // settingsRow artık kullanılmıyor (visual düzen tabloya taşındı)
  // function settingsRow(item) { ... }


  const configRows = [
    {
      group: "Bot Scan",
      name: "Taranacak Coin Sayısı",
      description: "Binance USDT evreninden volume sıralamasına göre kaç coin alınacağını belirler.",
      standard: defaults.scan_limit,
      value: current("bot", "scan_limit", localStorage.getItem("hmtstc_spot_universe_limit") || defaults.scan_limit),
      section: "bot",
      key: "scan_limit",
      type: "number",
      editable: true,
      effect: "ilk havuz",
      tone: "ok"
    },
    {
      group: "Bot Scan",
      name: "Deep Analiz Limiti",
      description: "Kaç coin için RSI, EMA, MACD ve teknik volatilite hesabı yapılacağını belirler.",
      standard: defaults.scan_deep_analysis_limit,
      value: current("bot", "scan_deep_analysis_limit", defaults.scan_deep_analysis_limit),
      section: "bot",
      key: "scan_deep_analysis_limit",
      type: "number",
      editable: true,
      effect: "teknik analiz",
      tone: "ok"
    },
    {
      group: "Likidite",
      name: "Minimum USDT Hacim",
      description: "24 saatlik USDT bazlı işlem hacmi bu değerin altındaysa coin elenir.",
      standard: "1,000,000 USDT",
      value: current("coin_filter", "min_quote_volume", defaults.min_quote_volume),
      section: "coin_filter",
      key: "min_quote_volume",
      type: "number",
      editable: true,
      effect: "low_quote_volume",
      tone: "warn"
    },
    {
      group: "Likidite",
      name: "Minimum İşlem Adedi",
      description: "Son 24 saatteki işlem sayısı bu değerin altındaysa coin yeterince aktif kabul edilmez.",
      standard: defaults.min_trade_count,
      value: current("coin_filter", "min_trade_count", defaults.min_trade_count),
      section: "coin_filter",
      key: "min_trade_count",
      type: "number",
      editable: true,
      effect: "low_trade_count",
      tone: "warn"
    },
    {
      group: "Volatilite",
      name: "Minimum Volatilite %",
      description: "Coinin yeterli fiyat hareketi üretip üretmediğini kontrol eder.",
      standard: defaults.min_volatility,
      value: current("coin_filter", "min_volatility", defaults.min_volatility),
      section: "coin_filter",
      key: "min_volatility",
      type: "number",
      editable: true,
      effect: "low_volatility",
      tone: "warn"
    },
    {
      group: "Likidite",
      name: "Maksimum Spread %",
      description: "İşleme uygunluk kontrolünde kabul edilen en yüksek alış-satış farkını belirler.",
      standard: defaults.max_spread_percent,
      value: current("risk", "max_spread_percent", defaults.max_spread_percent),
      section: "risk",
      key: "max_spread_percent",
      type: "number",
      editable: true,
      effect: "wide_spread",
      tone: "warn"
    },
    {
      group: "Volume",
      name: "Hacim Artış Çarpanı",
      description: "Yakın hacmin önceki ortalamaya göre kaç kat güçlü olması gerektiğini belirler.",
      standard: defaults.volume_growth_multiplier,
      value: current("coin_filter", "volume_growth_multiplier", defaults.volume_growth_multiplier),
      section: "coin_filter",
      key: "volume_growth_multiplier",
      type: "number",
      editable: true,
      effect: "weak_volume_growth",
      tone: "warn"
    },
    {
      group: "RSI",
      name: "RSI Min 15m",
      description: "15 dakikalık RSI alt sınırı.",
      standard: defaults.rsi_min_15m,
      value: current("coin_filter", "rsi_min_15m", defaults.rsi_min_15m),
      section: "coin_filter",
      key: "rsi_min_15m",
      type: "number",
      editable: true,
      effect: "rsi_out_of_range",
      tone: "warn"
    },
    {
      group: "RSI",
      name: "RSI Max 15m",
      description: "15 dakikalık RSI üst sınırı.",
      standard: defaults.rsi_max_15m,
      value: current("coin_filter", "rsi_max_15m", defaults.rsi_max_15m),
      section: "coin_filter",
      key: "rsi_max_15m",
      type: "number",
      editable: true,
      effect: "rsi_out_of_range",
      tone: "warn"
    },
    {
      group: "RSI",
      name: "RSI Min 1h",
      description: "1 saatlik RSI alt sınırı.",
      standard: defaults.rsi_min_1h,
      value: current("coin_filter", "rsi_min_1h", defaults.rsi_min_1h),
      section: "coin_filter",
      key: "rsi_min_1h",
      type: "number",
      editable: true,
      effect: "rsi_out_of_range",
      tone: "warn"
    },
    {
      group: "RSI",
      name: "RSI Max 1h",
      description: "1 saatlik RSI üst sınırı.",
      standard: defaults.rsi_max_1h,
      value: current("coin_filter", "rsi_max_1h", defaults.rsi_max_1h),
      section: "coin_filter",
      key: "rsi_max_1h",
      type: "number",
      editable: true,
      effect: "rsi_out_of_range",
      tone: "warn"
    },
    {
      group: "RSI",
      name: "RSI Min 4h",
      description: "4 saatlik RSI alt sınırı.",
      standard: defaults.rsi_min_4h,
      value: current("coin_filter", "rsi_min_4h", defaults.rsi_min_4h),
      section: "coin_filter",
      key: "rsi_min_4h",
      type: "number",
      editable: true,
      effect: "rsi_out_of_range",
      tone: "warn"
    },
    {
      group: "RSI",
      name: "RSI Max 4h",
      description: "4 saatlik RSI üst sınırı.",
      standard: defaults.rsi_max_4h,
      value: current("coin_filter", "rsi_max_4h", defaults.rsi_max_4h),
      section: "coin_filter",
      key: "rsi_max_4h",
      type: "number",
      editable: true,
      effect: "rsi_out_of_range",
      tone: "warn"
    },
    {
      group: "Evren",
      name: "Hariç Coinler",
      description: "Manuel olarak tarama dışında bırakılacak semboller.",
      standard: defaults.excluded_symbols,
      value: current("coin_filter", "excluded_symbols", defaults.excluded_symbols),
      section: "coin_filter",
      key: "excluded_symbols",
      type: "string",
      editable: true,
      effect: "excluded_symbol",
      tone: "warn"
    },
    {
      group: "Teknik Kural",
      name: "EMA Kontrolü",
      description: "EMA 9 / EMA 21 hizalaması teknik analiz aşamasında uygulanır.",
      standard: defaults.ema_rule,
      value: defaults.ema_rule,
      editable: false,
      effect: "ema_not_aligned",
      tone: "warn"
    },
    {
      group: "Teknik Kural",
      name: "MACD Kontrolü",
      description: "MACD 12 / 26 doğrulaması teknik analiz aşamasında uygulanır.",
      standard: defaults.macd_rule,
      value: defaults.macd_rule,
      editable: false,
      effect: "macd_negative",
      tone: "warn"
    },
    {
      group: "Kalite",
      name: "Kalite Skoru Alt Limiti",
      description: "Coin kalite skoru bu değerin altındaysa teknik aday reddedilir.",
      standard: defaults.quality_score_min,
      value: defaults.quality_score_min,
      key: "quality_score_min",
      editable: false,
      effect: "low_quality_score",
      tone: "warn"
    },
    {
      group: "Kalite",
      name: "Lightweight Skor Limiti",
      description: "Hızlı market taramasında minimum aday skoru. Skor bu değerin altındaysa coin aday olmaz.",
      standard: defaults.lightweight_score_min,
      value: current("coin_filter", "lightweight_score_min", defaults.lightweight_score_min),
      section: "coin_filter",
      key: "lightweight_score_min",
      type: "number",
      editable: true,
      effect: "score_below_threshold",
      tone: "warn"
    }
  ];

  function statusOf(row) {
    if (row.passed === true) return "GEÇTİ";
    const status = String(row.status || "").toUpperCase();
    return status || "ELENDİ";
  }

  function reasonOf(row) {
    if (row.first_rejection_reason) return reasonLabel(row.first_rejection_reason);
    const list = Array.isArray(row.rejection_reasons) ? row.rejection_reasons : [];
    if (list.length) return list.map(reasonLabel).join(", ");
    return reasonLabel(row.reason || row.reject_reason || row.top_reason || "-");
  }

  function boolSignal(value) {
    if (value === true) return "OK";
    if (value === false) return "RED";
    return "-";
  }

  const tableRows = scanRows.slice(0, 500).map(function (row) {
    const passed = row.passed === true || String(row.status || "").toLowerCase().indexOf("pass") !== -1;

    return "<tr>" +
      "<td><b>" + esc(row.symbol || row.coin || "-") + "</b><small>" + esc(row.analysis_depth || "-") + "</small></td>" +
      "<td>" + esc(fmt(row.price, 8)) + "</td>" +
      "<td>" + esc(fmt(row.quote_volume || row.volume_today || row.volume, 2)) + "</td>" +
      "<td>" + esc(row.trade_count || "-") + "</td>" +
      "<td>" + esc(fmt(row.volatility, 2)) + "</td>" +
      "<td>" + esc(row.rsi_15m || row.rsi || "-") + "</td>" +
      "<td>" + esc(row.rsi_1h || "-") + "</td>" +
      "<td>" + esc(row.rsi_4h || "-") + "</td>" +
      "<td>" + esc(row.volume_growth === undefined ? "-" : boolSignal(row.volume_growth)) + "</td>" +
      "<td>" + esc(boolSignal(row.ema_signal)) + "</td>" +
      "<td>" + esc(boolSignal(row.macd_signal)) + "</td>" +
      "<td>" + esc(fmt(row.quality_score, 2)) + "</td>" +
      "<td><span class='status-pill " + (passed ? "ok" : "warn") + "'>" + esc(statusOf(row)) + "</span></td>" +
      "<td>" + esc(reasonOf(row)) + "</td>" +
    "</tr>";
  }).join("");

  const totalSeen = scan.universe_total_seen || scan.scanned || scanRows.length || 0;
  const eligible = scan.eligible_universe_count || scan.scanned || scanRows.length || 0;
  const candidateCount = scan.candidates_count || candidates.length || scanRows.filter(function (item) { return item.passed === true; }).length;
  const rejectedCount = scan.rejected_count || Math.max(Number(eligible) - Number(candidateCount), 0);
  const universeRejected = scan.universe_rejected_count || 0;
  const lastTime = scan.time || scan.last_scan_at || scan.scan_time || scan.updated_at || "-";
  const visibleConfigRows = configRows.filter(function (item) {
    if (item.key === "scan_deep_analysis_limit" && !isAdmin) return false;
    return true;
  });
  function settingsTableRow(item) {
    const userValue = item.editable
      ? inputCell(item.section, item.key, item.type || "string", item.value, item.standard)
      : "<span class='cf-readonly-value'>" + esc(item.value) + "</span>";

    return "<tr class='cf-param-row'>" +
      "<td class='cf-param-name'>" + esc(item.name) + "</td>" +
      "<td class='cf-param-group'>" + esc(item.group || "") + "</td>" +
      "<td class='cf-param-desc'>" + esc(item.description) + "</td>" +
      "<td class='cf-param-std'>" + esc(item.standard) + "</td>" +
      "<td class='cf-param-rejects'>" + rejectionCountCell(item) + "</td>" +
      "<td class='cf-param-value'>" + userValue + "</td>" +
    "</tr>";

  }

  const parameterGrid = "<div class='cf-parameter-table-wrap' style='max-width:50%;'>" +
    "<table class='cf-parameter-table'><colgroup>" +
    "<col style='width:22%;'/><col style='width:10%;'/><col style='width:22%;'/><col style='width:10%;'/><col style='width:16%;'/><col style='width:20%;'/>" +
    "</colgroup><thead><tr>" +


      "<th>Parametre</th>" +
      "<th>Grup</th>" +
      "<th>Açıklama</th>" +
      "<th>Standart</th>" +
      "<th>Elendi (Son Scan)</th>" +
      "<th>Kullanıcı Değeri</th>" +
    "</tr></thead><tbody>" +
    visibleConfigRows.map(settingsTableRow).join("") +
    "</tbody></table></div>";
  const actionButtons = "<div class='buttons compact-buttons cf-action-row'>" +

    "<button type='button' class='btn btn-main' " + (HMTSTC_APP.state.coinFilterSaving ? "disabled " : "") + "onclick='HMTSTC_COIN_FILTER_ACTIONS.save(event)'>" + (HMTSTC_APP.state.coinFilterSaving ? "Kaydediliyor..." : "Ayarları Kaydet") + "</button>" +
    "<button type='button' class='btn btn-ghost' onclick='HMTSTC_COIN_FILTER_ACTIONS.fetchLastScan()'>Son Scan Verisini Yenile</button>" +
    "<button type='button' class='btn btn-ghost' " + (HMTSTC_APP.state.coinFilterTestScanRunning ? "disabled " : "") + "onclick='HMTSTC_COIN_FILTER_ACTIONS.runTestScan()'>" + (HMTSTC_APP.state.coinFilterTestScanRunning ? "Test scan çalışıyor..." : "Test Scan Çalıştır") + "</button>" +
  "</div>";

  return "<div class='coin-filter-wrap observation-page cf-control-page'>" +
    HMTSTC_UI.card(
      "<div class='mini-page-head'>" +
        "<div>" +
          "<h2>CoinFilter Kontrol Merkezi</h2>" +
          "<span>Botun piyasayı hangi girdilerle taradığını, hangi kriterlerle elediğini ve son scan sonucunu gösterir.</span>" +
        "</div>" +
        "<div class='status-pill ok'>BOT SCAN</div>" +
      "</div>" +
      "<div class='history-summary-grid operational-metrics settings-health-grid coin-universe-summary'>" +
        "<div><span>Toplam Görülen Coin</span><b>" + esc(totalSeen) + "</b></div>" +
        "<div><span>Stable/Leveraged/Geçersiz Elenen</span><b>" + esc(universeRejected) + "</b></div>" +
        "<div><span>Likiditeyi Geçen</span><b>" + esc(eligible) + "</b></div>" +
        "<div><span>Teknik Filtreden Geçen</span><b>" + esc(candidateCount) + "</b></div>" +
        "<div><span>Final CoinFilter Adayı</span><b>" + esc(candidateCount) + "</b></div>" +
        "<div><span>Son Scan Zamanı</span><b>" + esc(String(lastTime).replace("T", " ").slice(0, 19)) + "</b></div>" +
      "</div>" +
      actionButtons +
      (HMTSTC_APP.state.coinFilterScanLoading ? "<div class='muted-line'>Son tarama önbellekten yenileniyor...</div>" : "") +
      (HMTSTC_APP.state.coinFilterSaveMessage ? "<div class='muted-line cf-save-status " + esc(HMTSTC_APP.state.coinFilterSaveStatus || "idle") + "'>" + esc(HMTSTC_APP.state.coinFilterSaveMessage) + "</div>" : ""),
      "premium-settings-panel"
    ) +

    HMTSTC_UI.card(
      "<div class='section-title'><span>CoinFilter Parametreleri</span><small>Sadece karar akışında kullanılan kullanıcı ayarları</small></div>" + parameterGrid + actionButtons,
      "ops-panel"
    ) +

    HMTSTC_UI.card(
      "<div class='section-title'><span>Son Bot Scan Detayı</span><small>Coin bazında geçti / elendi / sebep / teknik değerler</small></div>" +
      "<div class='table-wrap fixed-scroll-panel tall'><table><thead><tr>" +
        "<th>Coin</th><th>Fiyat</th><th>24h USDT hacim</th><th>Trade count</th><th>Volatilite</th><th>RSI 15m</th><th>RSI 1h</th><th>RSI 4h</th><th>Volume growth</th><th>EMA</th><th>MACD</th><th>Quality score</th><th>Durum</th><th>Elenme sebebi</th>" +
      "</tr></thead><tbody>" +
        (tableRows || "<tr><td colspan='14'>" + (hasCachedScan ? "Bu taramada gösterilecek coin satırı yok." : "Henüz canlı tarama yok") + "</td></tr>") +
      "</tbody></table></div>",
      "ops-panel"
    ) +
  "</div>";
};
