window.HMTSTC_APP_SETTINGS = {
  numberFields: [
    "min_quote_volume",
    "min_trade_count",
    "min_volatility",
    "volatility_candle_count",
    "rsi_min_15m",
    "rsi_min_1h",
    "rsi_min_4h",
    "rsi_max_15m",
    "rsi_max_1h",
    "rsi_max_4h",
    "volume_growth_multiplier",
    "quality_score_min",
    "lightweight_score_min"
  ],

  settingsFieldMap: {
    "Test Modu": ["api", "mode", "string"],

    "Varsayılan Mod": ["bot", "default_mode", "string"],
    "Max Açık Pozisyon": ["bot", "max_open_positions", "number"],
    "USDT / Pozisyon": ["bot", "usdt_per_position", "number"],
    "Bot Bütçesi USDT": ["bot", "allocated_usdt", "number"],

    "Günlük Zarar Limiti": ["risk", "daily_loss_limit", "string"],
    "Haftalık Zarar Limiti": ["risk", "weekly_loss_limit", "string"],
    "Stop Loss": ["risk", "stop_loss", "string"],
    "Kar Hedefi": ["risk", "take_profit", "string"],
    "Max Portföy Risk %": ["risk", "max_portfolio_risk_percent", "number"],
    "Pozisyon Risk %": ["risk", "risk_per_position_percent", "number"],
    "Max Aynı Yön Pozisyon": ["risk", "max_same_direction_positions", "number"],

    "Chat ID": ["telegram", "chat_id_saved", "booleanByLength"],

    "Minimum USDT Hacim": ["coin_filter", "min_quote_volume", "number"],
    "Minimum İşlem Adedi": ["coin_filter", "min_trade_count", "number"],
    "Min Volatilite %": ["coin_filter", "min_volatility", "number"],
    "Volatilite Mum Sayısı": ["coin_filter", "volatility_candle_count", "number"],
    "Volatilite Periyodu": ["coin_filter", "volatility_interval", "string"],

    "RSI Min 15m": ["coin_filter", "rsi_min_15m", "number"],
    "RSI Min 1h": ["coin_filter", "rsi_min_1h", "number"],
    "RSI Min 4h": ["coin_filter", "rsi_min_4h", "number"],

    "RSI Max 15m": ["coin_filter", "rsi_max_15m", "number"],
    "RSI Max 1h": ["coin_filter", "rsi_max_1h", "number"],
    "RSI Max 4h": ["coin_filter", "rsi_max_4h", "number"],

    "Hacim Çarpanı": ["coin_filter", "volume_growth_multiplier", "number"],
    "Hacim Artış Çarpanı": ["coin_filter", "volume_growth_multiplier", "number"],
    "Kalite Skoru Alt Limiti": ["coin_filter", "quality_score_min", "number"],
    "Lightweight Skor Limiti": ["coin_filter", "lightweight_score_min", "number"],

    "Hariç Coinler": ["coin_filter", "excluded_symbols", "string"]
  },

  getDefaultCoinFilter: function () {
    return {
      min_quote_volume: 1000000,
      min_trade_count: 1000,
      min_volatility: 0.4,
      volatility_candle_count: 12,
      volatility_interval: "15m",

      rsi_min_15m: 50,
      rsi_min_1h: 50,
      rsi_min_4h: 50,

      rsi_max_15m: 75,
      rsi_max_1h: 75,
      rsi_max_4h: 75,

      volume_growth_multiplier: 1,
      quality_score_min: 45,
      lightweight_score_min: 55,

      excluded_symbols: "USDCUSDT,FDUSDUSDT,BUSDUSDT,TUSDUSDT,DAIUSDT,EURUSDT,USDPUSDT"
    };
  },

  getDefaultSettings: function () {
    return {
      api: {
        mode: "live",
        binance_status: "not_configured",
        api_key_saved: false
      },
      bot: {
        default_mode: "live",
        max_open_positions: 5,
        usdt_per_position: 200,
        allocated_usdt: 1000
      },
      risk: {
        profile: "balanced",
        daily_loss_limit: 30,
        weekly_loss_limit: 90,
        stop_loss: 0.75,
        take_profit: 2,
        max_portfolio_risk_percent: 5,
        risk_per_position_percent: 1,
        dynamic_position_size: false,
        volatility_stop_enabled: false,
        max_same_direction_positions: 3
      },
      telegram: {
        enabled: false,
        chat_id_saved: false
      },
      coin_filter: this.getDefaultCoinFilter(),
      strategies: [],
      current_strategy: ""
    };
  },

  clone: function (value) {
    try {
      return JSON.parse(JSON.stringify(value || {}));
    } catch (error) {
      return {};
    }
  },

  toNumber: function (value, fallback) {
    if (value === null || value === undefined) {
      return fallback;
    }

    let raw = String(value).trim()
      .replace(/USDT/ig, "")
      .replace(/%/g, "")
      .replace(/\s+/g, "");

    if (raw.indexOf(",") !== -1 && raw.indexOf(".") !== -1) {
      raw = raw.lastIndexOf(",") > raw.lastIndexOf(".") ? raw.replace(/\./g, "").replace(",", ".") : raw.replace(/,/g, "");
    } else {
      raw = raw.replace(",", ".");
    }

    if (raw === "") {
      return fallback;
    }

    const parsed = Number(raw);

    if (!Number.isFinite(parsed)) {
      return fallback;
    }

    return parsed;
  },

  cleanString: function (value, fallback) {
    const text = String(value === null || value === undefined ? "" : value).trim();

    if (!text && fallback !== undefined) {
      return fallback;
    }

    return text;
  },

  normalizeExcludedSymbols: function (value, fallback) {
    const source = this.cleanString(value, fallback || this.getDefaultCoinFilter().excluded_symbols);
    const seen = {};
    const symbols = [];

    source.split(",").forEach(function (item) {
      const symbol = String(item || "").trim().replace(/\s+/g, "").toUpperCase();
      if (!symbol || seen[symbol]) return;
      seen[symbol] = true;
      symbols.push(symbol);
    });

    return symbols.join(",");
  },

  normalizeCoinFilter: function (coinFilter) {
    const defaults = this.getDefaultCoinFilter();
    const source = Object.assign({}, defaults, coinFilter || {});

    return {
      min_quote_volume: Math.max(0, this.toNumber(source.min_quote_volume, defaults.min_quote_volume)),
      min_trade_count: Math.max(0, Math.round(this.toNumber(source.min_trade_count, defaults.min_trade_count))),
      min_volatility: Math.max(0, this.toNumber(source.min_volatility, defaults.min_volatility)),
      volatility_candle_count: Math.max(1, Math.round(this.toNumber(source.volatility_candle_count, defaults.volatility_candle_count))),
      volatility_interval: this.cleanString(source.volatility_interval, defaults.volatility_interval),

      rsi_min_15m: this.toNumber(source.rsi_min_15m, defaults.rsi_min_15m),
      rsi_min_1h: this.toNumber(source.rsi_min_1h, defaults.rsi_min_1h),
      rsi_min_4h: this.toNumber(source.rsi_min_4h, defaults.rsi_min_4h),

      rsi_max_15m: this.toNumber(source.rsi_max_15m, defaults.rsi_max_15m),
      rsi_max_1h: this.toNumber(source.rsi_max_1h, defaults.rsi_max_1h),
      rsi_max_4h: this.toNumber(source.rsi_max_4h, defaults.rsi_max_4h),

      volume_growth_multiplier: Math.max(0, this.toNumber(source.volume_growth_multiplier, defaults.volume_growth_multiplier)),
      quality_score_min: Math.max(0, this.toNumber(source.quality_score_min, defaults.quality_score_min)),
      lightweight_score_min: Math.max(0, this.toNumber(source.lightweight_score_min, defaults.lightweight_score_min)),

      excluded_symbols: this.normalizeExcludedSymbols(source.excluded_symbols, defaults.excluded_symbols)
    };
  },

  normalizeSettings: function (settings) {
    const defaults = this.getDefaultSettings();
    const normalized = Object.assign({}, defaults, settings || {});

    normalized.api = Object.assign({}, defaults.api, normalized.api || {});
    normalized.bot = Object.assign({}, defaults.bot, normalized.bot || {});
    normalized.risk = Object.assign({}, defaults.risk, normalized.risk || {});
    normalized.telegram = Object.assign({}, defaults.telegram, normalized.telegram || {});
    normalized.coin_filter = this.normalizeCoinFilter(normalized.coin_filter || {});

    normalized.bot.max_open_positions = Math.max(
      1,
      Math.round(this.toNumber(normalized.bot.max_open_positions, defaults.bot.max_open_positions))
    );

    normalized.bot.usdt_per_position = Math.max(
      1,
      this.toNumber(normalized.bot.usdt_per_position, defaults.bot.usdt_per_position)
    );

    normalized.bot.allocated_usdt = Math.max(
      normalized.bot.usdt_per_position,
      this.toNumber(normalized.bot.allocated_usdt, defaults.bot.allocated_usdt)
    );

    normalized.risk.max_portfolio_risk_percent = Math.max(
      0,
      this.toNumber(normalized.risk.max_portfolio_risk_percent, defaults.risk.max_portfolio_risk_percent)
    );

    normalized.risk.risk_per_position_percent = Math.max(
      0,
      this.toNumber(normalized.risk.risk_per_position_percent, defaults.risk.risk_per_position_percent)
    );

    normalized.risk.stop_loss = Math.max(0, this.toNumber(normalized.risk.stop_loss, defaults.risk.stop_loss));
    normalized.risk.take_profit = Math.max(0, this.toNumber(normalized.risk.take_profit, defaults.risk.take_profit));
    normalized.risk.daily_loss_limit = Math.max(0, this.toNumber(normalized.risk.daily_loss_limit, defaults.risk.daily_loss_limit));
    normalized.risk.weekly_loss_limit = Math.max(0, this.toNumber(normalized.risk.weekly_loss_limit, defaults.risk.weekly_loss_limit));
    normalized.risk.max_slippage_percent = Math.max(0, this.toNumber(normalized.risk.max_slippage_percent || 0.35, 0.35));
    normalized.risk.max_spread_percent = Math.max(0, this.toNumber(normalized.risk.max_spread_percent || 0.35, 0.35));

    normalized.risk.max_same_direction_positions = Math.max(
      1,
      Math.round(this.toNumber(normalized.risk.max_same_direction_positions, defaults.risk.max_same_direction_positions))
    );

    if (!Array.isArray(normalized.strategies)) {
      normalized.strategies = [];
    }

    normalized.current_strategy = this.cleanString(normalized.current_strategy, "");

    return normalized;
  },

  getSettings: function () {
    const current = HMTSTC_DATA.settings || {};
    const normalized = this.normalizeSettings(current);

    HMTSTC_DATA.settings = normalized;

    return normalized;
  },

  getCoinFilterDraft: function () {
    const settings = this.getSettings();

    if (!HMTSTC_APP.state.coinFilterDraft) {
      HMTSTC_APP.state.coinFilterDraft = this.normalizeCoinFilter(settings.coin_filter || {});
    }

    return HMTSTC_APP.state.coinFilterDraft;
  },

  setCoinFilterValue: function (key, value) {
    const draft = this.getCoinFilterDraft();

    if (this.numberFields.indexOf(key) !== -1) {
      draft[key] = this.toNumber(value, draft[key]);
    } else {
      draft[key] = value;
    }

    HMTSTC_APP.state.coinFilterDirty = true;
  },

  collectCoinFilterInputs: function () {
    const fields = document.querySelectorAll("[data-coin-filter-key]");
    const draft = this.getCoinFilterDraft();
    const self = this;

    fields.forEach(function (input) {
      const key = input.getAttribute("data-coin-filter-key");

      if (!key) {
        return;
      }

      const value = input.value;

      if (self.numberFields.indexOf(key) !== -1) {
        draft[key] = self.toNumber(value, draft[key]);
      } else {
        draft[key] = value;
      }
    });

    return this.normalizeCoinFilter(draft);
  },

  saveCoinFilter: async function () {
    try {
      if (!HMTSTC_APP.state.auth) {
        HMTSTC_APP.pushOperationLine("HATA: Oturum yok. CoinFiltre kaydedilemedi.");
        return;
      }

      const draft = this.collectCoinFilterInputs();

      const result = await HMTSTC_APP.fetchJson("/api/settings/coin-filter", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "Cache-Control": "no-store"
        },
        body: JSON.stringify(draft)
      });

      HMTSTC_DATA.settings = this.getSettings();
      HMTSTC_DATA.settings.coin_filter = this.normalizeCoinFilter(result.coin_filter || draft);

      HMTSTC_APP.state.coinFilterDraft = Object.assign(
        {},
        HMTSTC_DATA.settings.coin_filter
      );

      HMTSTC_APP.state.coinFilterDirty = false;

      HMTSTC_APP.pushOperationLine("CoinFiltre kaydedildi.");
      HMTSTC_APP.render();

    } catch (error) {
      console.error("CoinFiltre kaydetme hatası:", error);
      HMTSTC_APP.pushOperationLine("HATA: CoinFiltre kaydedilemedi.");

      if (typeof alert === "function") {
        alert("CoinFiltre kaydedilemedi");
      }
    }
  },

  applyMappedField: function (settings, mapItem, value) {
    if (!mapItem || mapItem.length < 3) {
      return;
    }

    const section = mapItem[0];
    const key = mapItem[1];
    const type = mapItem[2];

    settings[section] = settings[section] || {};

    if (type === "number") {
      settings[section][key] = this.toNumber(value, settings[section][key]);
      return;
    }

    if (type === "booleanByLength") {
      settings[section][key] = String(value || "").trim().length > 0;
      return;
    }

    settings[section][key] = String(value === null || value === undefined ? "" : value).trim();
  },

  collectVisibleSettings: function (settings) {
    const inputs = document.querySelectorAll(".field");
    const self = this;

    settings = this.normalizeSettings(settings);

    inputs.forEach(function (field) {
      const label = field.querySelector("span");
      const input = field.querySelector("input, select, textarea");

      if (!input) {
        return;
      }

      const explicitPath = input.getAttribute("data-settings-path");

      if (explicitPath) {
        const parts = explicitPath.split(".");

        if (parts.length === 2) {
          const section = parts[0];
          const key = parts[1];

          settings[section] = settings[section] || {};

          if (input.type === "checkbox") {
            settings[section][key] = Boolean(input.checked);
          } else if (input.getAttribute("data-type") === "number") {
            settings[section][key] = self.toNumber(input.value, settings[section][key]);
          } else {
            settings[section][key] = String(input.value || "").trim();
          }
        }

        return;
      }

      if (!label) {
        return;
      }

      const name = label.textContent.trim();
      const value = input.type === "checkbox" ? input.checked : input.value;
      const mapItem = self.settingsFieldMap[name];

      if (!mapItem) {
        return;
      }

      self.applyMappedField(settings, mapItem, value);
    });

    return this.normalizeSettings(settings);
  },

  previewSettings: async function () {
    try {
      if (!HMTSTC_APP.state.auth) {
        HMTSTC_APP.pushOperationLine("HATA: Oturum yok. Risk önizleme yapılamadı.");
        return;
      }
      const currentSettings = this.collectVisibleSettings(
        this.clone(HMTSTC_DATA.settings || this.getDefaultSettings())
      );
      const result = await HMTSTC_APP.fetchJson("/api/settings/risk-preview", {
        method: "POST",
        headers: { "Content-Type": "application/json", "Cache-Control": "no-store" },
        body: JSON.stringify(currentSettings)
      });
      HMTSTC_DATA.settingsPreview = result;
      HMTSTC_APP.pushOperationLine("Risk önizleme hesaplandı: " + (result.status || "ok"));
      HMTSTC_APP.render();
    } catch (error) {
      console.error("Risk önizleme hatası:", error);
      HMTSTC_APP.pushOperationLine("HATA: Risk önizleme yapılamadı.");
      if (typeof alert === "function") alert(HMTSTC_APP.apiErrorMessage ? HMTSTC_APP.apiErrorMessage(error, "Risk önizleme yapılamadı") : "Risk önizleme yapılamadı");
    }
  },


  previewRiskImpact: async function () {
    try {
      if (!HMTSTC_APP.state.auth) {
        HMTSTC_APP.pushOperationLine("HATA: Oturum yok. Risk impact hesaplanamadı.");
        return;
      }
      const currentSettings = this.collectVisibleSettings(
        this.clone(HMTSTC_DATA.settings || this.getDefaultSettings())
      );
      const result = await HMTSTC_APP.fetchJson("/api/settings/risk-impact", {
        method: "POST",
        headers: { "Content-Type": "application/json", "Cache-Control": "no-store" },
        body: JSON.stringify(currentSettings)
      });
      HMTSTC_DATA.settingsRiskImpact = result;
      HMTSTC_APP.pushOperationLine("Risk impact hesaplandı: " + (result.status || "ok"));
      HMTSTC_APP.render();
    } catch (error) {
      console.error("Risk impact hatası:", error);
      HMTSTC_APP.pushOperationLine("HATA: Risk impact hesaplanamadı.");
      if (typeof alert === "function") alert(HMTSTC_APP.apiErrorMessage ? HMTSTC_APP.apiErrorMessage(error, "Risk impact hesaplanamadı") : "Risk impact hesaplanamadı");
    }
  },

  previewSettingsRollback: async function (index) {
    try {
      const result = await HMTSTC_APP.fetchJson("/api/settings/rollback-preview", {
        method: "POST",
        headers: { "Content-Type": "application/json", "Cache-Control": "no-store" },
        body: JSON.stringify({ index: index })
      });
      HMTSTC_DATA.settingsRollbackPreview = result;
      HMTSTC_APP.pushOperationLine("Settings rollback preview üretildi: " + (result.status || "ok"));
      HMTSTC_APP.render();
    } catch (error) {
      console.error("Rollback preview hatası:", error);
      HMTSTC_APP.pushOperationLine("HATA: Rollback preview üretilemedi.");
      if (typeof alert === "function") alert(HMTSTC_APP.apiErrorMessage ? HMTSTC_APP.apiErrorMessage(error, "Rollback preview üretilemedi") : "Rollback preview üretilemedi");
    }
  },

  applySettingsRollback: async function (index) {
    try {
      if (typeof confirm === "function" && !confirm("Settings rollback yeni settings kaydı olarak uygulanacak. Devam edilsin mi?")) return;
      const result = await HMTSTC_APP.fetchJson("/api/settings/rollback", {
        method: "POST",
        headers: { "Content-Type": "application/json", "Cache-Control": "no-store" },
        body: JSON.stringify({ index: index })
      });
      HMTSTC_DATA.settings = this.normalizeSettings(result.settings || HMTSTC_DATA.settings);
      HMTSTC_DATA.settingsRollbackPreview = result.rollback_preview || {};
      HMTSTC_APP.pushOperationLine("Settings rollback uygulandı: " + (result.status || "saved"));
      HMTSTC_APP.render();
    } catch (error) {
      console.error("Rollback uygulama hatası:", error);
      HMTSTC_APP.pushOperationLine("HATA: Rollback uygulanamadı.");
      if (typeof alert === "function") alert(HMTSTC_APP.apiErrorMessage ? HMTSTC_APP.apiErrorMessage(error, "Rollback uygulanamadı") : "Rollback uygulanamadı");
    }
  },

  saveSettings: async function () {
    try {
      if (!HMTSTC_APP.state.auth) {
        HMTSTC_APP.pushOperationLine("HATA: Oturum yok. Ayarlar kaydedilemedi.");
        return;
      }

      const activeElement = document.activeElement;

      if (activeElement && activeElement.blur) {
        activeElement.blur();
      }

      const currentSettings = this.collectVisibleSettings(
        this.clone(HMTSTC_DATA.settings || this.getDefaultSettings())
      );

      if (
        currentSettings.bot &&
        currentSettings.bot.allocated_usdt < currentSettings.bot.usdt_per_position
      ) {
        currentSettings.bot.allocated_usdt = currentSettings.bot.usdt_per_position;
      }

      const result = await HMTSTC_APP.fetchJson("/api/settings", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "Cache-Control": "no-store"
        },
        body: JSON.stringify(currentSettings)
      });

      HMTSTC_DATA.settings = this.normalizeSettings(result.settings || currentSettings);

      HMTSTC_APP.state.coinFilterDraft = Object.assign(
        {},
        HMTSTC_DATA.settings.coin_filter || this.getDefaultCoinFilter()
      );

      HMTSTC_APP.state.coinFilterDirty = false;

      HMTSTC_APP.pushOperationLine("Ayarlar kaydedildi.");
      HMTSTC_APP.render();

    } catch (error) {
      console.error("HMTSTC settings kaydetme hatası:", error);
      HMTSTC_APP.pushOperationLine("HATA: Settings kaydedilemedi.");

      if (typeof alert === "function") {
        alert("Settings kaydedilemedi");
      }
    }
  },

  buildStrategyPayload: function () {
    const settings = this.getSettings();
    const strategies = Array.isArray(settings.strategies)
      ? settings.strategies
      : [];

    return {
      current_strategy: settings.current_strategy || "",
      strategies: strategies.map(function (strategy) {
        return Object.assign({}, strategy || {});
      })
    };
  },

  saveStrategySettings: async function () {
    if (HMTSTC_APP.state.strategySaving) {
      return;
    }

    try {
      if (!HMTSTC_APP.state.auth) {
        HMTSTC_APP.pushOperationLine("HATA: Oturum yok. Strateji ayarları kaydedilemedi.");
        return;
      }

      HMTSTC_APP.state.strategySaving = true;

      const payload = this.buildStrategyPayload();

      const result = await HMTSTC_APP.fetchJson("/api/settings/strategies", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "Cache-Control": "no-store"
        },
        body: JSON.stringify(payload)
      });

      HMTSTC_DATA.settings = this.getSettings();
      HMTSTC_DATA.settings.current_strategy = result.current_strategy || payload.current_strategy;
      HMTSTC_DATA.settings.strategies = Array.isArray(result.strategies)
        ? result.strategies
        : payload.strategies;

      HMTSTC_APP.state.strategyDirty = false;

      HMTSTC_APP.pushOperationLine("Strateji ayarları kaydedildi.");
      HMTSTC_APP.render();

    } catch (error) {
      console.error("Strateji kaydetme hatası:", error);
      HMTSTC_APP.state.strategyDirty = true;
      HMTSTC_APP.pushOperationLine("HATA: Strateji ayarları kaydedilemedi.");

    } finally {
      HMTSTC_APP.state.strategySaving = false;
    }
  },

  setCurrentStrategy: function (name) {
    const settings = this.getSettings();
    const strategies = Array.isArray(settings.strategies)
      ? settings.strategies
      : [];

    const target = strategies.find(function (item) {
      return item && item.name === name;
    });

    if (!target) {
      HMTSTC_APP.pushOperationLine("Strateji bulunamadı: " + name);
      return;
    }

    target.active = true;

    settings.current_strategy = name;
    settings.strategies = strategies;

    HMTSTC_DATA.settings = settings;

    HMTSTC_APP.state.strategyDirty = true;

    HMTSTC_APP.pushOperationLine("Strateji seçildi: " + name);

    HMTSTC_APP.render();
    this.saveStrategySettings();
  },

  toggleStrategy: function (name) {
    const settings = this.getSettings();
    const strategies = Array.isArray(settings.strategies)
      ? settings.strategies
      : [];

    const target = strategies.find(function (item) {
      return item && item.name === name;
    });

    if (!target) {
      HMTSTC_APP.pushOperationLine("Strateji bulunamadı: " + name);
      return;
    }

    const isActive = target.active !== false;

    if (settings.current_strategy === name && isActive) {
      HMTSTC_APP.pushOperationLine("Seçili strateji pasif yapılamaz: " + name);
      return;
    }

    target.active = !isActive;

    settings.strategies = strategies;

    HMTSTC_DATA.settings = settings;

    HMTSTC_APP.state.strategyDirty = true;

    HMTSTC_APP.pushOperationLine(
      "Strateji " + (target.active ? "aktif" : "pasif") + " yapıldı: " + name
    );

    HMTSTC_APP.render();
    this.saveStrategySettings();
  }
};
