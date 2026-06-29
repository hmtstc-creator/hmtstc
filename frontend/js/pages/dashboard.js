window.HMTSTC_PAGES = window.HMTSTC_PAGES || {};

window.HMTSTC_PRODUCT_UI = {
  esc: function (value) {
    return HMTSTC_APP.escapeHtml(value === undefined || value === null ? "" : value);
  },

  num: function (value, fallback) {
    const parsed = Number(value);
    return Number.isFinite(parsed) ? parsed : (fallback || 0);
  },

  money: function (value) {
    return this.num(value, 0).toFixed(2) + " USDT";
  }
};

(function () {
  const ui = window.HMTSTC_PRODUCT_UI;

  function data() {
    return window.HMTSTC_DATA || {};
  }

  function dashboard() {
    return data().dashboard || {};
  }

  function reports() {
    return data().reports || {};
  }

  window.HMTSTC_DASHBOARD_JARVIS = window.HMTSTC_DASHBOARD_JARVIS || {
    setBotControlMode: async function (mode) {
      const cleanMode = ["closed", "open", "automatic"].indexOf(mode) === -1 ? "closed" : mode;

      if (!window.HMTSTC_APP || !HMTSTC_APP.fetchJson) return false;

      const settings = HMTSTC_APP.clone
        ? HMTSTC_APP.clone(HMTSTC_DATA.settings || {})
        : JSON.parse(JSON.stringify(HMTSTC_DATA.settings || {}));

      settings.bot = Object.assign({}, settings.bot || {}, {
        control_mode: cleanMode
      });

      settings.auto_bot_mode = Object.assign({}, settings.auto_bot_mode || {}, {
        enabled: cleanMode === "automatic",
        control_mode: cleanMode
      });

      try {
        const result = await HMTSTC_APP.fetchJson("/api/settings", {
          method: "POST",
          requestKind: "mutation",
          preventGlobalAbort: true,
          timeoutMs: 15000,
          headers: {
            "Content-Type": "application/json",
            "Cache-Control": "no-store"
          },
          body: JSON.stringify(settings)
        });

        HMTSTC_DATA.settings = result.settings || settings;
        HMTSTC_APP.pushOperationLine("Bot kontrol tercihi kaydedildi: " + cleanMode);

        await HMTSTC_APP.syncApiData();

        return true;
      } catch (error) {
        HMTSTC_APP.pushOperationLine("HATA: Bot kontrol tercihi kaydedilemedi.");

        if (typeof alert === "function") {
          alert(HMTSTC_APP.apiErrorMessage ? HMTSTC_APP.apiErrorMessage(error, "Bot kontrol tercihi kaydedilemedi.") : "Bot kontrol tercihi kaydedilemedi.");
        }

        return false;
      }
    },

    activateOpenMode: async function () {
      const saved = await this.setBotControlMode("open");
      if (saved && window.HMTSTC_APP && HMTSTC_APP.startBot) await HMTSTC_APP.startBot();
    },

    activateClosedMode: async function () {
      const saved = await this.setBotControlMode("closed");
      if (saved && window.HMTSTC_APP && HMTSTC_APP.stopBot) await HMTSTC_APP.stopBot();
    },

    activateAutomaticMode: async function () {
      const saved = await this.setBotControlMode("automatic");
      if (saved && window.HMTSTC_APP && HMTSTC_APP.startBot) await HMTSTC_APP.startBot();
    },

    recordNoTradeReason: function (reason) {
      const text = String(reason || "").trim();
      if (!text) return;

      const minuteKey = new Date().toISOString().slice(0, 16);
      if (this.lastNoTradeMinute === minuteKey) return;

      this.lastNoTradeMinute = minuteKey;

      const list = Array.isArray(HMTSTC_DATA.dashboardNoTradeReasons)
        ? HMTSTC_DATA.dashboardNoTradeReasons
        : [];

      list.push({
        time: new Date().toLocaleTimeString("tr-TR", {
          hour: "2-digit",
          minute: "2-digit"
        }),
        reason: text
      });

      HMTSTC_DATA.dashboardNoTradeReasons = list.slice(-30);
    }
  };

  function activeRuleIds(source) {
    return Array.isArray(source)
      ? source.map(function (item) {
          if (!item || item.enabled === false || item.active === false) return "";
          return String(item.id || item.name || "");
        }).filter(Boolean)
      : [];
  }

  function selectionState(draftIds, backendIds, fallbackAll, lastKnownIds) {
    if (Array.isArray(draftIds)) {
      return {
        ids: draftIds.map(String),
        explicit: true,
        source: "draft"
      };
    }

    if (Array.isArray(backendIds)) {
      return {
        ids: backendIds.map(String),
        explicit: true,
        source: "backend"
      };
    }

    if (Array.isArray(lastKnownIds)) {
      return {
        ids: lastKnownIds.map(String),
        explicit: true,
        source: "last_known"
      };
    }

    return {
      ids: [],
      explicit: true,
      source: Array.isArray(fallbackAll) && fallbackAll.length ? "no_backend_selection" : "no_rules"
    };
  }

  function normalizeIdList(list) {
    const seen = {};

    return (Array.isArray(list) ? list : [])
      .map(function (item) { return String(item || "").trim(); })
      .filter(function (item) {
        if (!item || seen[item]) return false;
        seen[item] = true;
        return true;
      })
      .sort();
  }

  function sameIdSet(left, right) {
    const leftIds = normalizeIdList(left);
    const rightIds = normalizeIdList(right);

    if (leftIds.length !== rightIds.length) return false;

    return leftIds.every(function (item, index) {
      return item === rightIds[index];
    });
  }

  function recordDashboardRuleSelectionProof(selectedFilters, selectedStrategies) {
    const appState = ((window.HMTSTC_APP || {}).state || null);
    if (!appState) return;

    const rendered = {
      filter: normalizeIdList((selectedFilters || {}).ids),
      strategy: normalizeIdList((selectedStrategies || {}).ids),
      filter_source: (selectedFilters || {}).source || "",
      strategy_source: (selectedStrategies || {}).source || "",
      updated_at: new Date().toLocaleTimeString("tr-TR")
    };
    appState.dashboardRenderedRuleSelection = rendered;

    if (!appState.rulesSelectionProof || typeof appState.rulesSelectionProof !== "object") return;

    appState.rulesSelectionProof.render_filter_ids = rendered.filter.slice();
    appState.rulesSelectionProof.render_strategy_ids = rendered.strategy.slice();
    appState.rulesSelectionProof.render_filter_source = rendered.filter_source;
    appState.rulesSelectionProof.render_strategy_source = rendered.strategy_source;
    appState.rulesSelectionProof.render_filter_matches_payload = sameIdSet(appState.rulesSelectionProof.payload_filter_ids, rendered.filter);
    appState.rulesSelectionProof.render_strategy_matches_payload = sameIdSet(appState.rulesSelectionProof.payload_strategy_ids, rendered.strategy);
  }

  function checkList(kind, source, selection, attr) {
      const list = Array.isArray(source) && source.length ? source.slice(0, 18) : [];
      const state = selection && typeof selection === "object"
        ? selection
        : { ids: [], explicit: true, source: "empty_selection" };
      const selectedIds = Array.isArray(state.ids) ? state.ids.map(String) : [];

      if (!list.length) {
        return '<div class="jarvis-empty-mini"><b>Kayıt yok</b><span>Sync sonrası dolacak.</span></div>';
      }

      const draftKind = attr.indexOf("strategy") !== -1 ? "strategy" : "filter";

      return list.map(function (item, index) {
        const id = String(item.id || item.name || (kind + "-" + (index + 1)));
        const name = item.name || item.title || id;
        const checked = selectedIds.indexOf(id) !== -1 ? " checked" : "";

        return '<label class="jarvis-toggle-row">' +
          "<span>" + ui.esc(name) + "</span>" +
          '<input type="checkbox" ' + attr +
            ' value="' + ui.esc(id) + '"' +
            checked +
            ' onchange="HMTSTC_APP.updateDashboardRuleDraft(\'' + draftKind + '\', this.value, this.checked)" />' +
        "</label>";
      }).join("");
  }




  window.HMTSTC_PAGES.dashboard = function () {
    const d = dashboard();
    const bot = data().botStatus || {};
    const settings = data().settings || {};
    const botSettings = settings.bot || {};
    const risk = settings.risk || {};
    const positions = Array.isArray(data().positions) ? data().positions : [];
    const history = Array.isArray(data().history) ? data().history : [];
    const scan = normalizeDashboardScan(data().botScan || {});
    const funnel = scan.funnel_summary || {};
    const strategyRuntime = scan.strategy_runtime && typeof scan.strategy_runtime === "object" ? scan.strategy_runtime : {};
    const decision = scan.karabasan_runtime || data().tradeabilityDecision60 || data().autoBotModeDecision61 || {};
    const api = ((data().meApiConnection67 || {}).api_connection) || data().meApiConnection67 || {};
    const publicApi = api.public_connection || {};
    const apiTradeEnabled = Boolean(api.trade_enabled || api.can_execute_real_trade || publicApi.can_trade);
    const rules = data().rules || {};
    const filters = Array.isArray(rules.filters) ? rules.filters : [];
    const strategies = Array.isArray(rules.strategies) ? rules.strategies : [];
    const dashboardRuleDraft = (((window.HMTSTC_APP || {}).state || {}).dashboardRuleSelectionDraft) || {};
    const lastKnownSelection = (((window.HMTSTC_APP || {}).state || {}).lastKnownRulesSelection) || {};
    const selectedFilters = selectionState(dashboardRuleDraft.filter, rules.selected_filter_ids, filters, lastKnownSelection.filter);
    const selectedStrategies = selectionState(dashboardRuleDraft.strategy, rules.selected_strategy_ids, strategies, lastKnownSelection.strategy);
    recordDashboardRuleSelectionProof(selectedFilters, selectedStrategies);
    const ruleSelectionSaving = Boolean(((window.HMTSTC_APP || {}).state || {}).dashboardRuleSelectionSaving);
     const role = String(((window.HMTSTC_APP || {}).state || {}).role || "user").toLowerCase();


    function normalizeDashboardScan(payload) {
      const scan = payload && typeof payload === "object" ? payload : {};
      const diag = scan.scan_diagnostics && typeof scan.scan_diagnostics === "object" ? scan.scan_diagnostics : {};
      return Object.assign({}, scan, {
        time: scan.time || scan.scan_time || scan.last_scan_at || null,
        filter_rejection_counts: (scan.filter_rejection_counts && typeof scan.filter_rejection_counts === "object") ? scan.filter_rejection_counts : ((diag.filter_rejection_counts && typeof diag.filter_rejection_counts === "object") ? diag.filter_rejection_counts : {}),
        candidates: Array.isArray(scan.candidates) ? scan.candidates : [],
        scan_rows: Array.isArray(scan.scan_rows) ? scan.scan_rows : [],
        candidate_handoff: scan.candidate_handoff && typeof scan.candidate_handoff === "object"
          ? scan.candidate_handoff
          : { contract: "coinfilter_candidate_handoff_v1", candidates: [], passed: 0 }
      });
    }

    function line(label, value) {
      return '<div class="dash-jarvis-line">' +
        "<span>" + ui.esc(label) + "</span>" +
        "<b>" + ui.esc(value) + "</b>" +
      "</div>";
    }

    function statusClass(status) {
      const clean = String(status || "").toLowerCase();
      if (["ok", "online", "ready", "active", "running", "connected", "good"].indexOf(clean) !== -1) return "good";
      if (["warning", "syncing", "starting", "automatic", "waiting", "review", "deferred", "degraded"].indexOf(clean) !== -1) return "warn";
      if (["error", "offline", "blocked", "empty_rules", "not_connected", "bad"].indexOf(clean) !== -1) return "bad";
      return "idle";
    }

    function systemStatusItem(label, value, status, note) {
      return '<div class="dashboard-system-status-item status-' + ui.esc(statusClass(status)) + '">' +
        "<span>" + ui.esc(label) + "</span>" +
        "<b>" + ui.esc(value || "-") + "</b>" +
        "<small>" + ui.esc(note || "") + "</small>" +
      "</div>";
    }

    function formatCompactTime(value) {
      if (!value) return "-";
      const date = new Date(value);
      if (!isNaN(date.getTime())) {
        return date.toLocaleTimeString("tr-TR", { hour: "2-digit", minute: "2-digit" });
      }
      return String(value).replace("T", " ").slice(0, 16);
    }

    function renderSystemStatusStrip() {
      const system = data().systemStatus || {};
      const lastApiErrorType = String(system.last_api_error_type || "");
      const lastApiRequestKind = String(system.last_api_request_kind || "core_read");
      const coreSensitiveError = ["backend_offline", "timeout", "cors_error", "http_500"].indexOf(lastApiErrorType) !== -1;
      const coreError = coreSensitiveError && lastApiRequestKind === "core_read";
      const backendStatus = lastApiErrorType === "request_aborted"
        ? (system.backend_api || "online")
        : (system.backend_api
        || (["http_401", "http_403", "http_404"].indexOf(lastApiErrorType) !== -1 ? "online" : "")
        || (coreError ? "offline" : "")
        || (HMTSTC_APP.state.apiReady || HMTSTC_APP.state.apiSyncReady ? "online" : "offline"));
      const backendLabel = backendStatus === "online" ? "Online" : (backendStatus === "offline" ? "Offline" : "Hata");
      const authExpired = system.auth_status === "auth_expired" || lastApiErrorType === "http_401" || HMTSTC_APP.state.auth === false;
      const authForbidden = system.auth_status === "forbidden" || lastApiErrorType === "http_403";
      const authLabel = authExpired ? "Süresi Doldu" : (authForbidden ? "Yetki Yok" : "Geçerli");
      const heavyStatus = String(system.heavy_status || "ready");
      const heavyLabel = heavyStatus === "timeout" ? "Timeout" : (heavyStatus === "degraded" ? "Uyarı" : (heavyStatus === "syncing" || heavyStatus === "deferred" ? "Gecikiyor" : "Hazır"));
      const auditStatus = String(system.audit_status || "pending");
      const auditLabel = auditStatus === "written" ? "Yazıldı" : (auditStatus === "warning" ? "Uyarı" : "Beklemede");
      const rulesPreserved = Boolean(system.rules_payload_preserved || rules.preserved_after_empty_payload);
      const rulesLabel = rulesPreserved ? "Son Liste Korunuyor" : "Hazır";
      const botRunning = bot.bot_running === true;
      const botEngine = String(bot.engine_status || "").toLowerCase();
      const botStatus = botRunning
        ? "running"
        : (["starting", "restoring"].indexOf(botEngine) !== -1
          ? "starting"
          : (["error", "failed", "stale"].indexOf(botEngine) !== -1 ? "error" : "idle"));
      const botLabel = botRunning ? "Açık" : (botEngine === "starting" ? "Başlatılıyor" : (botEngine === "error" ? "Hata" : "Kapalı"));
      const karabasanScore = firstValue(decision, ["karabasan_score", "score", "market_confidence_score"], "-");
      const karabasanDecision = String(firstValue(decision, ["decision", "market_mode", "status"], "-"));
      const karabasanBlocked = /block|yasak|stop|kapalı/i.test(karabasanDecision);
      const karabasanStatus = karabasanBlocked ? "blocked" : (karabasanScore === "-" ? "idle" : "ok");
      const paperLab = data().paperLabStatus || {};
      const reportsPayload = reports().paper_lab || {};
      const paperModelCount = paperLab.model_count !== undefined ? paperLab.model_count : (reportsPayload.models_count || funnel.active_models || 0);
      const paperStatus = paperLab.status || (paperModelCount > 0 ? "ready" : "warning");
      const ruleStore = rules.rule_store_status || {};
      const ruleFilterCount = ruleStore.active_filter_count !== undefined ? ruleStore.active_filter_count : filters.length;
      const ruleStrategyCount = ruleStore.active_strategy_count !== undefined ? ruleStore.active_strategy_count : strategies.length;
      const ruleStoreBad = Boolean(ruleStore.empty_active_backup_available || (!ruleFilterCount && !ruleStrategyCount));
      const binanceConnected = Boolean(api.connected || api.public_ok || publicApi.connected || publicApi.can_read || api.trade_enabled);

      return '<div class="dashboard-system-status-strip">' +
        systemStatusItem("Backend API", backendLabel, backendStatus, system.last_api_error_message || system.last_api_ok_at || "-") +
        systemStatusItem("Oturum", authLabel, authExpired || authForbidden ? "bad" : "good", system.auth_message || HMTSTC_APP.state.loginError || "-") +
        systemStatusItem("Ağır Analiz", heavyLabel, heavyStatus === "timeout" ? "warn" : "good", system.heavy_message || "-") +
        systemStatusItem("Audit", auditLabel, auditStatus === "warning" ? "warn" : (auditStatus === "written" ? "good" : "idle"), system.audit_message || "-") +
        systemStatusItem("Rules", rulesLabel, rulesPreserved ? "warn" : "good", system.rules_payload_review_note || "-") +
        systemStatusItem("Bot Durumu", botLabel, botStatus, bot.stop_reason || bot.runtime_text || "-") +
        systemStatusItem("Karabasan", karabasanBlocked ? "Blokluyor" : (karabasanScore === "-" ? "Skor Yok" : "Aktif"), karabasanStatus, "Skor: " + karabasanScore + " / " + karabasanDecision) +
        systemStatusItem("Paper Lab", paperStatus === "syncing" ? "Senkronize" : (paperModelCount > 0 ? "Hazır" : "Model Yok"), paperStatus, "Model: " + paperModelCount) +
        systemStatusItem("Rule Store", ruleFilterCount + " filtre / " + ruleStrategyCount + " strateji", ruleStoreBad ? "bad" : "ok", ruleStore.message || formatCompactTime(rules.last_activation_at)) +
        systemStatusItem("Binance API", binanceConnected ? "Bağlı" : (api.status === "error" ? "Bağlı Değil" : "Test Edilmedi"), binanceConnected ? "connected" : "idle", api.message || publicApi.message || "-") +
      "</div>";
    }

    function panel(cls, title, body) {
      return '<section class="dash-jarvis-panel ' + cls + '">' +
        (title ? "<h3>" + ui.esc(title) + "</h3>" : "") +
        body +
      "</section>";
    }

    function rulesPanel(body) {
      return '<section class="dash-jarvis-panel rules">' +
        '<div class="dashboard-rules-head">' +
          '<h3>Strateji / Filtre</h3>' +
          '<button type="button" class="btn btn-main btn-small dashboard-rules-save" ' +
            (ruleSelectionSaving ? "disabled " : "") +
            'onclick="HMTSTC_APP.saveDashboardRuleSelection()">' +
            (ruleSelectionSaving ? "Kaydediliyor..." : "Kaydet") +
          "</button>" +
        '</div>' +
        body +
      "</section>";
    }

    function firstValue(item, keys, fallback) {
      for (let i = 0; i < keys.length; i += 1) {
        const value = item ? item[keys[i]] : undefined;
        if (value !== undefined && value !== null && value !== "") return value;
      }

      return fallback || "-";
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
        score_below_threshold: "Skor eşiği altı",
        no_candidate: "Uygun aday yok",
        paper_lab_model_yok: "Paper Lab modeli yok",
        strategy_or_risk_no_trade: "Strateji/risk işlem açtırmadı"
      };

      return map[reason] || reason || "-";
    }

    function renderTradeHistoryTable() {
        const rows = history.slice(-80).reverse();

        function formatDateTime(value) {
          if (!value) return "-";

          const date = new Date(value);

          if (!isNaN(date.getTime())) {
            return date.toLocaleString("tr-TR", {
              day: "2-digit",
              month: "2-digit",
              hour: "2-digit",
              minute: "2-digit"
            });
          }

          return String(value).replace("T", " ").slice(0, 16);
        }

        if (!rows.length) {
          return '<div class="jarvis-empty-mini"><b>İşlem geçmişi yok</b><span>Gerçekleşen işlemler burada tablo olarak görünecek.</span></div>';
        }

        return '<div class="dashboard-trade-table-wrap">' +
          '<table class="dashboard-trade-table">' +
            "<thead>" +
              "<tr>" +
                "<th>Tarih & Saat</th>" +
                "<th>Coin</th>" +
                "<th>Alım</th>" +
                "<th>Satış</th>" +
                "<th>Kazanç</th>" +
                "<th>Kazanç %</th>" +
                "<th>Strateji</th>" +
              "</tr>" +
            "</thead>" +
            "<tbody>" +
              rows.map(function (item) {
                const time = firstValue(item, ["exit_time", "closed_at", "close_time", "time", "entry_time", "created_at"], "-");
                const symbol = firstValue(item, ["symbol", "coin", "pair", "asset"], "-");
                const buy = firstValue(item, ["entry_price", "buy_price", "open_price", "entry", "avg_buy_price"], "-");
                const sell = firstValue(item, ["exit_price", "sell_price", "close_price", "exit", "avg_sell_price"], "-");
                const pnl = firstValue(item, ["net_pnl", "pnl", "profit", "realized_pnl"], 0);
                const pnlPct = firstValue(item, ["pnl_percent", "profit_percent", "realized_pnl_percent", "roi_percent"], "-");
                const strategy = firstValue(item, ["strategy_name", "strategy", "strategy_id", "model_id"], "-");

                return "<tr>" +
                  "<td>" + ui.esc(formatDateTime(time)) + "</td>" +
                  "<td><b>" + ui.esc(symbol) + "</b></td>" +
                  "<td>" + ui.esc(buy) + "</td>" +
                  "<td>" + ui.esc(sell) + "</td>" +
                  "<td><b>" + ui.esc(ui.num(pnl, 0).toFixed(2)) + "</b></td>" +
                  "<td>" + ui.esc(pnlPct === "-" ? "-" : String(pnlPct).replace("%", "") + "%") + "</td>" +
                  "<td>" + ui.esc(strategy) + "</td>" +
                "</tr>";
              }).join("") +
            "</tbody>" +
          "</table>" +
        "</div>";
    }

    function renderFunnelSummary() {
      const stages = Array.isArray(funnel.stages) && funnel.stages.length
        ? funnel.stages
        : [
            {
              key: "total_seen",
              label: "Toplam Görülen",
              value: scan.universe_total_seen || scan.scanned || 0,
              description: "Binance USDT evreninden görülen toplam parite."
            },
            {
              key: "eligible_universe",
              label: "Evrene Kalan",
              value: scan.eligible_universe_count || scan.scanned || 0,
              description: "Evren guardlarından sonra kalan coin."
            },
            {
              key: "technical_passed",
              label: "Teknik Geçen",
              value: scan.candidates_count || 0,
              description: "Teknik filtrelerden geçen aday coin."
            },
            {
              key: "active_models",
              label: "Aktif Model",
              value: funnel.active_models || ((reports().paper_lab || {}).models_count || 0),
              description: "Filtre + strateji kombinasyonu."
            },
            {
              key: "final_candidate_count",
              label: "Final Aday",
              value: funnel.final_candidate_count || scan.candidates_count || 0,
              description: "İşlem hattına girebilecek aday."
            },
            {
              key: "opened_symbol",
              label: "Açılan İşlem",
              value: funnel.opened_symbol || "-",
              description: "Son tick içinde açılan coin."
            }
          ];

      return '<div class="dashboard-funnel-flow">' +
        stages.map(function (item, index) {
          return '<div class="dashboard-funnel-step">' +
            '<span class="dashboard-funnel-index">' + ui.esc(index + 1) + "</span>" +
            "<b>" + ui.esc(item.value === undefined || item.value === null ? "-" : item.value) + "</b>" +
            "<strong>" + ui.esc(item.label || "-") + "</strong>" +
            "<em>" + ui.esc(item.description || "") + "</em>" +
          "</div>";
        }).join("") +
      "</div>";
    }

    function safeCount(value, fallback) {
      const parsed = Number(value);

      if (Number.isFinite(parsed) && parsed >= 0) return Math.floor(parsed);

      return Number.isFinite(Number(fallback)) && Number(fallback) >= 0
        ? Math.floor(Number(fallback))
        : 0;
    }

    function hasScanData() {
      return Boolean(
        scan.time ||
        scan.scan_id ||
        scan.source ||
        safeCount(scan.universe_total_seen, 0) > 0 ||
        safeCount(scan.scanned, 0) > 0 ||
        safeCount(scan.candidates_count, 0) > 0 ||
        (Array.isArray(scan.candidates) && scan.candidates.length) ||
        (Array.isArray(scan.scan_rows) && scan.scan_rows.length)
      );
    }

    function statusLabel(status) {
      const map = {
        ok: "OK",
        warning: "Bekle",
        blocked: "Blok",
        unknown: "Veri Yok"
      };

      return map[status] || map.unknown;
    }

    function stageStatus(passed, blocked, total, forceBlocked) {
      if (!total && !passed && !blocked) return "unknown";
      if (forceBlocked || (!passed && blocked > 0)) return "blocked";
      if (blocked > 0) return "warning";
      return "ok";
    }

    function makeStage(id, label, total, passed, blocked, reason, forceBlocked) {
      const cleanTotal = safeCount(total, 0);
      const cleanPassed = safeCount(passed, 0);
      const cleanBlocked = safeCount(blocked, 0);

      return {
        id: id,
        label: label,
        total: cleanTotal,
        passed: cleanPassed,
        blocked: cleanBlocked,
        status: stageStatus(cleanPassed, cleanBlocked, cleanTotal, forceBlocked),
        reason: reason || "Veri bekleniyor"
      };
    }

    function breakdownRows(source) {
      if (Array.isArray(source)) {
        return source.map(function (item) {
          return {
            reason: item.reason || item.key || item.label || "-",
            label: item.label || reasonLabel(item.reason || item.key),
            count: safeCount(item.count || item.value, 0)
          };
        }).filter(function (item) {
          return item.count > 0;
        });
      }

      if (!source || typeof source !== "object") return [];

      return Object.keys(source).map(function (key) {
        return {
          reason: key,
          label: reasonLabel(key),
          count: safeCount(source[key], 0)
        };
      }).filter(function (item) {
        return item.count > 0;
      });
    }

    function topBlockReasons() {
      const rows = []
        .concat(breakdownRows(scan.universe_rejection_breakdown))
        .concat(breakdownRows(scan.rejection_breakdown))
        .concat(breakdownRows(((funnel.breakdowns || {}).universe) || []))
        .concat(breakdownRows(((funnel.breakdowns || {}).technical) || []));

      if (!rows.length && scan.top_rejection_reason) {
        rows.push({
          reason: scan.top_rejection_reason,
          label: reasonLabel(scan.top_rejection_reason),
          count: safeCount(scan.rejected_count, 1)
        });
      }

      const merged = {};

      rows.forEach(function (item) {
        const key = item.label || item.reason || "-";
        merged[key] = (merged[key] || 0) + safeCount(item.count, 0);
      });

      return Object.keys(merged).map(function (key) {
        return {
          reason: key,
          count: merged[key]
        };
      }).sort(function (a, b) {
        return b.count - a.count;
      }).slice(0, 5);
    }

    function reasonFromRow(row) {
      const reasons = []
        .concat(Array.isArray(row.rejection_reasons) ? row.rejection_reasons : [])
        .concat(Array.isArray(row.reasons) ? row.reasons : [])
        .concat(Array.isArray(row.block_reasons) ? row.block_reasons : []);

      if (row.rejection_reason) reasons.push(row.rejection_reason);
      if (row.reason) reasons.push(row.reason);
      if (row.error) reasons.push(row.error);

      const first = reasons.filter(Boolean)[0];

      return first ? reasonLabel(first) : "-";
    }

    function decisionCandidateRows() {
      const handoff = scan.candidate_handoff || {};
      const candidates = Array.isArray(handoff.candidates) ? handoff.candidates : [];
      const rows = candidates.filter(function (row) { return row && row.passed === true; });

      return rows.slice(0, 10).map(function (row) {
        const reason = reasonFromRow(row);
        const symbol = firstValue(row, ["symbol", "coin", "pair", "asset"], "-");
        const score = firstValue(row, ["score", "quality_score", "total_score", "final_score"], "-");
        const hasReason = reason !== "-";
        const passed = row.passed === true || row.status === "passed" || row.status === "ok" || candidates.indexOf(row) !== -1;
        const opened = funnel.opened_symbol && String(funnel.opened_symbol) === String(symbol);
        const decisionText = opened ? "allowed" : (passed ? "candidate" : (hasReason ? "blocked" : "wait"));
        const riskBlocked = Boolean(row.risk_rejection_reason || row.risk_block_reason || row.karabasan_block_reason || (row.karabasan_decision && row.karabasan_decision.approved === false));

        return {
          symbol: symbol,
          filter_status: hasReason && !passed ? "blocked" : (passed ? "passed" : "unknown"),
          strategy_status: decisionText === "candidate" || decisionText === "allowed" ? "passed" : "unknown",
          risk_status: riskBlocked ? "blocked" : (decisionText === "allowed" ? "passed" : "unknown"),
          score: score,
          decision: decisionText,
          reason: opened ? "Son tick içinde işlem açıldı" : (reason === "-" ? buildNoTradeReason() : reason)
        };
      });
    }

    function compactStatus(value) {
      const map = {
        passed: "Geçti",
        blocked: "Blok",
        unknown: "Veri Yok",
        wait: "Bekle",
        candidate: "Aday",
        allowed: "İzin"
      };

      return map[value] || value || "-";
    }

    function buildDecisionFunnelModel() {
      if (!hasScanData()) {
        return {
          status: "empty",
          source: "empty",
          updated_at: null,
          bot_mode: bot.bot_running ? (bot.mode || botSettings.control_mode || "on") : "off",
          trade_allowed: false,
          final_reason: "Son tarama verisi yok. Bot çalışınca karar hunisi burada görünecek.",
          stages: [],
          candidates: [],
          top_block_reasons: []
        };
      }

      if (scan.error || (scan.status && scan.status !== "ok")) {
        return {
          status: "error",
          source: scan.source || "last_scan",
          updated_at: scan.time || null,
          bot_mode: bot.bot_running ? (bot.mode || botSettings.control_mode || "on") : "off",
          trade_allowed: false,
          final_reason: scan.error || scan.status || "Karar hunisi okunamadı.",
          stages: [],
          candidates: [],
          top_block_reasons: []
        };
      }

      const totalSeen = safeCount(scan.universe_total_seen, safeCount(scan.scanned, 0));
      const eligible = safeCount(scan.eligible_universe_count, safeCount(scan.scanned, 0));
      const universeRejected = safeCount(scan.universe_rejected_count, Math.max(totalSeen - eligible, 0));
      const technicalPassed = safeCount(scan.candidates_count, Array.isArray(scan.candidates) ? scan.candidates.length : 0);
      const technicalRejected = safeCount(scan.rejected_count, Math.max(eligible - technicalPassed, 0));
      const activeModels = safeCount(strategyRuntime.active_strategy_ids && strategyRuntime.active_strategy_ids.length, safeCount(funnel.active_models, ((reports().paper_lab || {}).models_count || 0)));
      const finalCandidates = safeCount(strategyRuntime.passed, safeCount(funnel.final_candidate_count, technicalPassed));
      const opened = funnel.opened_symbol ? 1 : 0;
      const finalBlocked = Math.max(finalCandidates - opened, 0);
      const mainReason = buildNoTradeReason();

      return {
        status: "ok",
        source: "last_scan",
        updated_at: scan.time || null,
        bot_mode: bot.bot_running ? (bot.mode || botSettings.control_mode || "on") : "off",
        trade_allowed: Boolean(opened),
        final_reason: opened ? "Son tick içinde işlem açıldı: " + funnel.opened_symbol : mainReason,
        stages: [
          makeStage("market_source", "Piyasa verisi", totalSeen, totalSeen, 0, scan.source ? "Piyasa verisi okundu: " + scan.source : "Piyasa verisi son taramadan okunuyor"),
          makeStage("universe", "Taranan coin", totalSeen, eligible, universeRejected, universeRejected > 0 ? universeRejected + " coin temel evren guardlarından elendi" : "Piyasa havuzu tarandı"),
          makeStage("filters", "Filtrelerden geçen", eligible, technicalPassed, technicalRejected, technicalRejected > 0 ? technicalRejected + " coin hacim/teknik filtrelerden elendi" : "Filtreleri geçen adaylar hazır"),
          makeStage("strategies", "Strateji sinyali", technicalPassed, finalCandidates, Math.max(technicalPassed - finalCandidates, 0), activeModels > 0 ? activeModels + " aktif model üzerinden sinyal değerlendirildi" : "Aktif Paper Lab modeli yok", activeModels < 1),
          makeStage("risk", "Risk / Karabasan", finalCandidates, decision.approved === true ? 1 : 0, decision.approved === true ? Math.max(finalCandidates - 1, 0) : finalCandidates, decision.explanation || decision.reason || decision.decision_text || "Risk/Karabasan sonucu mevcut karar verisinden izleniyor"),
          makeStage("final", "Final işlem adayı", finalCandidates, opened, finalBlocked, opened ? "Final işlem izni oluştu" : "Final işlem adayı oluşmadı. Sebep: " + mainReason, !opened && finalCandidates > 0)
        ],
        candidates: decisionCandidateRows(),
        top_block_reasons: topBlockReasons()
      };
    }

    function renderDecisionCandidateTable(rows) {
      if (!rows.length) {
        return '<div class="jarvis-empty-mini"><b>Aday tablo verisi yok</b><span>Son scan aday satırı üretince burada en fazla 10 coin görünecek.</span></div>';
      }

      return '<div class="dashboard-decision-table-wrap">' +
        '<table class="dashboard-decision-table">' +
          "<thead><tr>" +
            "<th>Coin</th><th>Filtre</th><th>Strateji</th><th>Risk</th><th>Skor</th><th>Karar</th><th>Sebep</th>" +
          "</tr></thead>" +
          "<tbody>" +
            rows.map(function (item) {
              return "<tr>" +
                "<td><b>" + ui.esc(item.symbol) + "</b></td>" +
                "<td>" + ui.esc(compactStatus(item.filter_status)) + "</td>" +
                "<td>" + ui.esc(compactStatus(item.strategy_status)) + "</td>" +
                "<td>" + ui.esc(compactStatus(item.risk_status)) + "</td>" +
                "<td>" + ui.esc(item.score) + "</td>" +
                "<td>" + ui.esc(compactStatus(item.decision)) + "</td>" +
                "<td>" + ui.esc(item.reason) + "</td>" +
              "</tr>";
            }).join("") +
          "</tbody>" +
        "</table>" +
      "</div>";
    }

    function renderTopBlockReasons(rows) {
      if (!rows.length) return "";

      return '<div class="dashboard-decision-reasons">' +
        rows.map(function (item) {
          return "<span>" + ui.esc(item.reason) + " <b>" + ui.esc(item.count) + "</b></span>";
        }).join("") +
      "</div>";
    }

    function renderDecisionFunnelPanel() {
      const model = buildDecisionFunnelModel();

      if (model.status === "empty") {
        return '<p class="dashboard-decision-subtitle">Bot neden işlem açmadı?</p>' +
          '<div class="jarvis-empty-mini dashboard-decision-empty"><b>Son tarama verisi yok.</b><span>Bot çalışınca karar hunisi burada görünecek.</span></div>';
      }

      if (model.status === "error") {
        return '<p class="dashboard-decision-subtitle">Bot neden işlem açmadı?</p>' +
          '<div class="jarvis-empty-mini dashboard-decision-empty"><b>Karar hunisi okunamadı.</b><span>Backend bağlantısı veya son tarama verisi kontrol edilmeli.</span></div>';
      }

      return '<p class="dashboard-decision-subtitle">Bot neden işlem açmadı?</p>' +
        '<div class="dashboard-decision-final">' +
          "<span>Final sebep</span>" +
          "<b>" + ui.esc(model.final_reason) + "</b>" +
        "</div>" +
        '<div class="dashboard-decision-stages">' +
          model.stages.map(function (stage) {
            return '<article class="dashboard-decision-stage status-' + ui.esc(stage.status) + '">' +
              '<div><strong>' + ui.esc(stage.label) + '</strong><span>' + ui.esc(statusLabel(stage.status)) + '</span></div>' +
              '<p><b>' + ui.esc(stage.passed) + '</b> geçen <em>' + ui.esc(stage.blocked) + ' elenen</em></p>' +
              '<small>' + ui.esc(stage.reason) + '</small>' +
            "</article>";
          }).join("") +
        "</div>" +
        renderDecisionCandidateTable(model.candidates) +
        renderTopBlockReasons(model.top_block_reasons);
    }

    function renderBreakdown(title, rows) {
      const list = Array.isArray(rows) ? rows.slice(0, 6) : [];

      if (!list.length) {
        return '<div class="jarvis-empty-mini"><b>' + ui.esc(title) + '</b><span>Bu kategoride red sebebi yok.</span></div>';
      }

      return '<div class="dashboard-breakdown-list">' +
        "<b>" + ui.esc(title) + "</b>" +
        list.map(function (item) {
          return "<div>" +
            "<span>" + ui.esc(item.label || reasonLabel(item.reason)) + "</span>" +
            "<strong>" + ui.esc(item.count || 0) + "</strong>" +
          "</div>";
        }).join("") +
      "</div>";
    }

    function buildNoTradeReason() {
      if (!bot.bot_running) return "Bot kapalı olduğu için işlem açılmadı.";

      if (funnel.main_block_label) {
        return funnel.main_block_label;
      }

      if (apiTradeEnabled === false && role !== "owner" && role !== "admin") {
        return "Kullanıcı gerçek işlem için API bağlantısı veya trade izni tamamlanmadığı için işlem açılamadı.";
      }

      if (decision.reason || decision.decision_text || decision.top_reason) {
        return decision.reason || decision.decision_text || decision.top_reason;
      }

      if (scan.top_rejection_reason) {
        return "Coin taramasında ana red sebebi: " + reasonLabel(scan.top_rejection_reason);
      }

      if ((scan.candidates_count || 0) < 1) {
        return "Final işlem adayı oluşmadı. Sebep: Coin taramasında filtre, strateji veya risk izni yeterli değil.";
      }

      if (positions.length >= Number(risk.max_open_positions || botSettings.max_open_positions || 999)) {
        return "Açık pozisyon limiti dolu olduğu için yeni işlem açılmadı.";
      }

      return "Final işlem adayı oluşmadı. Sebep: Strateji sinyali veya risk izni yeterli değil.";
    }

    function renderNoTradeReasonBox() {
      const logs = Array.isArray(HMTSTC_DATA.dashboardNoTradeReasons)
        ? HMTSTC_DATA.dashboardNoTradeReasons.slice(-8).reverse()
        : [];

      if (!logs.length) {
        return '<div class="jarvis-empty-mini"><b>Bekleniyor</b><span>İşlem açılamama nedeni 1 dakika içinde burada görünür.</span></div>';
      }

      return '<div class="dashboard-no-trade-log">' + logs.map(function (item) {
        return "<div>" +
          "<span>" + ui.esc(item.time || "-") + "</span>" +
          "<b>" + ui.esc(item.reason || "-") + "</b>" +
        "</div>";
      }).join("") + "</div>";
    }

    function controlMode() {
      const value = String(botSettings.control_mode || bot.control_mode || "closed").toLowerCase();
      if (["automatic", "auto", "otomatik"].indexOf(value) !== -1) return "automatic";
      if (bot.bot_running || bot.requested_running) return "open";
      return "closed";
    }

    function terminalStatus(label, value, state, detail) {
      return '<div class="terminal-status status-' + ui.esc(state || "idle") + '">' +
        '<span>' + ui.esc(label) + '</span>' +
        '<b>' + ui.esc(value) + '</b>' +
        '<small>' + ui.esc(detail || "") + '</small>' +
      '</div>';
    }

    function reasonCount(pattern) {
      const rows = []
        .concat(breakdownRows(scan.universe_rejection_breakdown))
        .concat(breakdownRows(scan.rejection_breakdown))
        .concat(breakdownRows(((funnel.breakdowns || {}).universe) || []))
        .concat(breakdownRows(((funnel.breakdowns || {}).technical) || []));
      const matching = rows.filter(function (item) {
        return pattern.test(String(item.reason || "") + " " + String(item.label || ""));
      });
      if (!matching.length) return "N/A";
      return matching.reduce(function (total, item) { return total + safeCount(item.count, 0); }, 0);
    }

    function renderBotControlCenter(mode) {
      const running = Boolean(bot.bot_running);
      const requested = Boolean(bot.requested_running);
      const engine = String(bot.engine_status || (running ? "running" : "stopped"));
      const operation = data().operation || {};
      const commandPending = String((((window.HMTSTC_APP || {}).state || {}).botCommandPending) || "");
      const commandDisabled = commandPending ? " disabled" : "";
      return '<section class="terminal-panel bot-control-center">' +
        '<div class="terminal-panel-head"><div><span>BOT CONTROL</span><h2>Çalışma Merkezi</h2></div><i class="terminal-live-dot ' + (running ? "is-live" : "") + '"></i></div>' +
        '<div class="bot-control-segments" role="group" aria-label="Bot çalışma modu">' +
          '<button type="button" class="bot-mode-button ' + (mode === "open" ? "active" : "") + '"' + commandDisabled + ' onclick="HMTSTC_DASHBOARD_JARVIS.activateOpenMode()"><span>▶</span>Açık</button>' +
          '<button type="button" class="bot-mode-button ' + (mode === "closed" ? "active" : "") + '"' + commandDisabled + ' onclick="HMTSTC_DASHBOARD_JARVIS.activateClosedMode()"><span>■</span>Kapalı</button>' +
          '<button type="button" class="bot-mode-button automatic ' + (mode === "automatic" ? "active" : "") + '"' + commandDisabled + ' onclick="HMTSTC_DASHBOARD_JARVIS.activateAutomaticMode()"><span>◆</span>Otomatik</button>' +
        '</div>' +
        '<button type="button" class="dashboard-emergency-stop" onclick="HMTSTC_APP.set({modal:true})"><span>!</span>Acil Stop</button>' +
        '<div class="runtime-mini-grid">' +
          '<div><span>İstek</span><b>' + (requested ? "RUN" : "STOP") + '</b></div>' +
          '<div><span>Engine</span><b>' + ui.esc(engine) + '</b></div>' +
          '<div><span>First tick</span><b>' + ui.esc(formatCompactTime(bot.last_tick || bot.last_tick_at)) + '</b></div>' +
          '<div><span>Scan worker</span><b>' + ui.esc(bot.scan_worker_alive === false ? "offline" : (bot.scan_worker_status || bot.worker_status || "cached")) + '</b></div>' +
        '</div>' +
        '<div class="bot-control-result"><span>Son işlem</span><p>' + ui.esc(operation.message || bot.primary_runtime_problem || bot.stop_reason || "Komut bekleniyor.") + '</p></div>' +
        '<div class="compact-rule-control">' +
          '<div class="compact-rule-head"><b>Kural Seçimi</b><button type="button" ' + (ruleSelectionSaving ? "disabled " : "") + 'onclick="HMTSTC_APP.saveDashboardRuleSelection()">' + (ruleSelectionSaving ? "Kaydediliyor" : "Kaydet") + '</button></div>' +
          '<div class="compact-rule-columns"><div><span>Filtre</span>' + checkList("Filtre", filters, selectedFilters, "data-rule-filter-select") + '</div><div><span>Strateji</span>' + checkList("Strateji", strategies, selectedStrategies, "data-rule-strategy-select") + '</div></div>' +
        '</div>' +
      '</section>';
    }

    function renderPortfolioPanel() {
      const latestCandidate = (Array.isArray(scan.candidates) && scan.candidates[0]) || (Array.isArray(scan.scan_rows) && scan.scan_rows[0]) || {};
      const openPnl = positions.reduce(function (total, item) {
        return total + ui.num(item.unrealized_pnl !== undefined ? item.unrealized_pnl : item.pnl, 0);
      }, 0);
      const positionRows = positions.slice(0, 5).map(function (item) {
        const pnl = ui.num(item.unrealized_pnl !== undefined ? item.unrealized_pnl : item.pnl, 0);
        return '<div class="terminal-position-row"><b>' + ui.esc(item.symbol || item.coin || "-") + '</b><span>' + ui.esc(item.side || item.direction || "-") + '</span><strong class="' + (pnl >= 0 ? "positive" : "negative") + '">' + ui.esc(pnl.toFixed(2)) + '</strong></div>';
      }).join("");
      return '<section class="terminal-panel portfolio-terminal">' +
        '<div class="terminal-panel-head"><div><span>PORTFOLIO</span><h2>Pozisyon Özeti</h2></div><small>' + ui.esc(positions.length) + ' açık</small></div>' +
        '<div class="portfolio-metrics">' +
          '<div><span>Bakiye</span><b>' + ui.money(d.wallet_value) + '</b></div>' +
          '<div><span>Günlük PnL</span><b class="' + (ui.num(d.daily_pnl, 0) >= 0 ? "positive" : "negative") + '">' + ui.money(d.daily_pnl) + '</b></div>' +
          '<div><span>Toplam PnL</span><b class="' + (ui.num(d.total_pnl, 0) >= 0 ? "positive" : "negative") + '">' + ui.money(d.total_pnl) + '</b></div>' +
          '<div><span>Açık PnL</span><b class="' + (openPnl >= 0 ? "positive" : "negative") + '">' + ui.money(openPnl) + '</b></div>' +
        '</div>' +
        '<div class="terminal-subsection"><span>Son sinyal / aday</span><div class="latest-signal"><b>' + ui.esc(latestCandidate.symbol || latestCandidate.coin || "Veri yok") + '</b><strong>' + ui.esc(firstValue(latestCandidate, ["score", "quality_score", "status", "decision"], "-")) + '</strong><small>' + ui.esc(reasonFromRow(latestCandidate)) + '</small></div></div>' +
        '<div class="terminal-subsection positions-list"><span>Açık pozisyonlar</span>' + (positionRows || '<p class="terminal-empty">Açık pozisyon yok.</p>') + '</div>' +
      '</section>';
    }

    function renderCoinFilterTerminal() {
      const diagnostic = scan.scan_diagnostics || {};
      const volume = diagnostic.volume_rejection_diagnostics || scan.volume_rejection_diagnostics || {};
      const total = scan.universe_total_seen !== undefined ? scan.universe_total_seen : scan.scanned;
      const eligible = scan.eligible_universe_count;
      const candidates = scan.candidates_count !== undefined ? scan.candidates_count : (Array.isArray(scan.candidates) ? scan.candidates.length : 0);
      const rejected = scan.rejected_count !== undefined ? scan.rejected_count : (Number.isFinite(Number(total)) && Number.isFinite(Number(eligible)) ? Math.max(Number(total) - Number(eligible), 0) : "N/A");
      const metrics = [
        ["Toplam görülen", total === undefined ? "N/A" : total],
        ["Taranan", scan.scanned === undefined ? "N/A" : scan.scanned],
        ["Aday", candidates],
        ["Elendi", rejected],
        ["Volume", volume.low_quote_volume_count !== undefined ? volume.low_quote_volume_count : reasonCount(/volume|hacim/i)],
        ["Liquidity", reasonCount(/liquidity|likidite/i)],
        ["Spread", reasonCount(/spread/i)],
        ["Strategy", reasonCount(/strategy|strateji/i)]
      ];
      return '<section class="terminal-panel coinfilter-terminal">' +
        '<div class="terminal-panel-head"><div><span>COINFILTER</span><h2>Son Tarama Özeti</h2></div><small>' + ui.esc(formatCompactTime(scan.time || scan.updated_at)) + '</small></div>' +
        '<div class="coinfilter-metric-strip">' + metrics.map(function (item) { return '<div><span>' + ui.esc(item[0]) + '</span><b>' + ui.esc(item[1]) + '</b></div>'; }).join("") + '</div>' +
        '<div class="volume-contract"><span>Etkin minimum hacim</span><b>' + ui.esc(volume.effective_min_quote_volume === undefined ? "N/A" : volume.effective_min_quote_volume) + '</b><small>USDT quote volume · quoteVolume_USDT_24h</small></div>' +
      '</section>';
    }

    function renderTerminalLogs() {
      const apiLogs = Array.isArray(data().logs) ? data().logs : [];
      const operationLines = Array.isArray((data().operation || {}).lines) ? data().operation.lines : [];
      const rows = apiLogs.slice(-16).map(function (item) {
        return { time: item.time || item.created_at || item.timestamp, level: item.level || item.status || "INFO", message: item.message || item.event || item.detail || JSON.stringify(item) };
      }).concat(operationLines.map(function (item) { return { time: "", level: "UI", message: item }; })).slice(-18).reverse();
      return '<section class="terminal-panel event-terminal">' +
        '<div class="terminal-panel-head"><div><span>EVENT STREAM</span><h2>Canlı Log / Son Olaylar</h2></div><small>' + ui.esc(rows.length) + ' kayıt</small></div>' +
        '<div class="terminal-log-list">' + (rows.length ? rows.map(function (item) {
          return '<div><time>' + ui.esc(formatCompactTime(item.time)) + '</time><b>' + ui.esc(item.level) + '</b><span>' + ui.esc(item.message) + '</span></div>';
        }).join("") : '<p class="terminal-empty">Henüz olay kaydı yok.</p>') + '</div>' +
      '</section>';
    }

    const noTradeReason = buildNoTradeReason();

    setTimeout(function () {
      if (window.HMTSTC_DASHBOARD_JARVIS && HMTSTC_DASHBOARD_JARVIS.recordNoTradeReason) {
        HMTSTC_DASHBOARD_JARVIS.recordNoTradeReason(noTradeReason);
      }
    }, 0);

    const mode = controlMode();
    const system = data().systemStatus || {};
    const backendState = String(system.backend_api || (HMTSTC_APP.state.apiReady ? "online" : "offline"));
    const botEngine = String(bot.engine_status || (bot.bot_running ? "running" : "stopped"));
    const apiConnected = Boolean(api.connected || api.public_ok || publicApi.connected || publicApi.can_read || apiTradeEnabled);
    const handoffCandidates = scan.candidate_handoff && Array.isArray(scan.candidate_handoff.candidates)
      ? scan.candidate_handoff.candidates
      : [];
    const candidateRows = handoffCandidates.filter(function (row) {
          return row && row.passed === true;
        });
    const networkRows = candidateRows;

    setTimeout(function () {
      if (window.HMTSTC_LIVE_TRADE_NETWORK) {
        HMTSTC_LIVE_TRADE_NETWORK.mount("#live-trade-network", {
          nodes: networkRows,
          positions: positions,
          botRunning: Boolean(bot.bot_running),
          automatic: mode === "automatic",
          allowPlaceholder: false
        });
      }
    }, 0);

    return '<div class="dashboard-terminal-page mode-' + ui.esc(mode) + '">' +
      '<div class="terminal-status-rail">' +
        terminalStatus("Backend API", backendState === "online" ? "Online" : (backendState === "offline" ? "Hata" : "Gecikmeli"), backendState === "online" ? "good" : "bad", system.last_api_error_message || system.last_api_ok_at || "Cached bundle") +
        terminalStatus("Bot", bot.bot_running ? "Açık" : (["starting", "restoring"].indexOf(botEngine) !== -1 ? "Başlatılıyor" : (botEngine === "failed" ? "Hata" : "Kapalı")), bot.bot_running ? "good" : (["starting", "restoring"].indexOf(botEngine) !== -1 ? "warn" : "idle"), bot.primary_runtime_problem || bot.stop_reason || botEngine) +
        terminalStatus("API Bağlantısı", apiConnected ? "Bağlı" : "Kontrol Bekliyor", apiConnected ? "good" : "warn", api.message || publicApi.message || "Binance read state") +
        terminalStatus("Güncel Mod", mode === "automatic" ? "Otomatik" : (mode === "open" ? "Açık" : "Kapalı"), mode === "automatic" ? "auto" : (mode === "open" ? "good" : "idle"), "Paper runtime") +
      '</div>' +
      '<div class="dashboard-terminal-grid">' +
        renderBotControlCenter(mode) +
        '<section class="terminal-panel network-terminal"><div class="terminal-panel-head"><div><span>LIVE TRADE NETWORK</span><h1>Filtreyi Geçen Coin Mesh</h1></div><div class="network-legend"><span class="long">Long</span><span class="short">Short</span><span class="neutral">Neutral</span></div></div><div id="live-trade-network" class="live-trade-network" data-animation-mode="' + ui.esc(mode) + '"><canvas aria-label="Filtreyi geçen canlı coin network"></canvas>' + (!networkRows.length ? '<div class="network-empty"><b>Filtreyi geçen coin yok</b><span>Bu alan sadece CoinFilter adaylarını gösterir.</span></div>' : '') + '</div></section>' +
        renderPortfolioPanel() +
      '</div>' +
      '<div class="dashboard-terminal-bottom">' + renderCoinFilterTerminal() + renderTerminalLogs() + '</div>' +
    '</div>';
  };
})();
