window.HMTSTC_APP_API = {
  API_REQUEST_KIND: {
    CORE_READ: "core_read",
    HEAVY_READ: "heavy_read",
    MUTATION: "mutation",
    AUTH_RESTORE: "auth_restore",
    AUDIT_BEST_EFFORT: "audit_best_effort"
  },

  getApiUrl: function (path) {
    const base = window.HMTSTC_API_BASE || "";
    return base + path;
  },

  getAuthHeaders: function (extraHeaders) {
    const headers = Object.assign({}, extraHeaders || {});
    const app = window.HMTSTC_APP || {};
    const state = app.state || {};
    const token = state.token || localStorage.getItem("hmtstc_token") || "";
    if (token) {
      headers.Authorization = "Bearer " + token;
    }
    return headers;
  },

  requestOptions: function (options) {
    const cleanOptions = Object.assign({ cache: "no-store" }, options || {});
    cleanOptions.headers = this.getAuthHeaders(cleanOptions.headers || {});
    return cleanOptions;
  },

  apiErrorMessage: function (error, fallback) {
    if (!error) {
      return fallback || "İşlem başarısız.";
    }

    return error.userMessage || error.message || fallback || "İşlem başarısız.";
  },

  classifyApiError: function (error, response, path, requestKind) {
    if (response) {
      if (response.status === 401) return "http_401";
      if (response.status === 403) return "http_403";
      if (response.status === 404) return "http_404";
      if (response.status >= 500) return "http_500";
      return "http_" + response.status;
    }

    if (error && error.name === "AbortError") return "request_aborted";

    const message = String((error && error.message) || "").toLowerCase();
    if (message.indexOf("cors") !== -1) return "cors_error";
    if (message.indexOf("failed to fetch") !== -1 || message.indexOf("networkerror") !== -1) return "backend_offline";

    return "unknown_network";
  },

  apiUserMessage: function (type, detail, path) {
    const endpoint = path ? String(path).split("?")[0] : "";

    if (type === "backend_offline") return "Backend çevrimdışı görünüyor. Sistem durumu kontrol edilmeli.";
    if (type === "cors_error") return "Backend erişimi CORS veya origin nedeniyle engellenmiş olabilir.";
    if (type === "timeout") return "Backend isteği zaman aşımına uğradı.";
    if (type === "request_aborted") return "İstek iptal edildi; tekrar deneyebilirsin.";
    if (type === "http_401") return "Oturum geçersiz. Yeniden giriş gerekli.";
    if (type === "http_403") return "Yetki yetersiz. Rol veya izin kontrol edilmeli.";
    if (type === "http_404") return "Endpoint bulunamadı: " + endpoint;
    if (type === "http_500") return "Backend hata verdi: " + (detail || "iç hata");
    if (type === "invalid_json") return "Backend geçersiz cevap döndürdü.";

    return detail || "Sınıflandırılamayan ağ hatası.";
  },

  isCoreEndpoint: function (path) {
    const cleanPath = String(path || "").split("?")[0];
    return [
      "/api/auth/me",
      "/api/dashboard/bundle",
      "/api/rules",
      "/api/rules/paper-lab/status",
      "/api/settings",
      "/api/bot/status"
    ].indexOf(cleanPath) !== -1;
  },

  decorateApiError: function (error, type, detail, path, status, requestKind) {
    const apiError = error instanceof Error ? error : new Error(detail || "API isteği başarısız.");
    apiError.apiErrorType = type;
    apiError.requestKind = requestKind || "core_read";
    apiError.status = status === undefined ? (apiError.status || 0) : status;
    apiError.detail = detail || apiError.detail || apiError.message;
    apiError.endpoint = path;
    apiError.userMessage = this.apiUserMessage(type, apiError.detail, path);
    const isCore = this.isCoreEndpoint(path) && (!requestKind || requestKind === this.API_REQUEST_KIND.CORE_READ);
    const isHeavy = requestKind === this.API_REQUEST_KIND.HEAVY_READ;
    const isAudit = requestKind === this.API_REQUEST_KIND.AUDIT_BEST_EFFORT;
    const isMutation = requestKind === this.API_REQUEST_KIND.MUTATION;
    const isAuthRestore = requestKind === this.API_REQUEST_KIND.AUTH_RESTORE || requestKind === "auth_restore";
    const previousSystem = HMTSTC_DATA.systemStatus || {};
    let backendApiStatus = previousSystem.backend_api || "online";
    let coreFailureCount = Number(previousSystem.core_failure_count || 0);

    if (type === "http_401" || type === "http_403" || type === "http_404") {
      backendApiStatus = "online";
    } else if (type === "request_aborted" || isHeavy || isAudit || isMutation || isAuthRestore) {
      backendApiStatus = previousSystem.backend_api || "online";
    } else if (isCore && (type === "http_500" || type === "backend_offline" || type === "timeout" || type === "cors_error")) {
      coreFailureCount += 1;
      backendApiStatus = coreFailureCount >= 2 ? "error" : (previousSystem.backend_api || "online");
    } else if (type === "http_500" || type === "backend_offline" || type === "timeout" || type === "cors_error") {
      backendApiStatus = previousSystem.backend_api || "online";
    }

    const authStatus = type === "http_401"
      ? "auth_expired"
      : (type === "http_403" ? "forbidden" : (previousSystem.auth_status || ""));
    HMTSTC_DATA.systemStatus = Object.assign({}, previousSystem, {
      backend_api: backendApiStatus,
      auth_status: authStatus,
      last_api_error_type: type,
      last_api_error_endpoint: path,
      last_api_error_message: apiError.userMessage,
      last_api_error_at: new Date().toLocaleTimeString("tr-TR"),
      last_api_request_kind: requestKind || "core_read",
      core_failure_count: isCore ? coreFailureCount : Number(previousSystem.core_failure_count || 0),
      last_core_api_error_at: isCore ? new Date().toLocaleTimeString("tr-TR") : previousSystem.last_core_api_error_at,
      heavy_status: isHeavy && type === "timeout" ? "timeout" : previousSystem.heavy_status,
      audit_status: isAudit && type === "request_aborted" ? "warning" : previousSystem.audit_status
    });
    return apiError;
  },

  clearRestrictedData: function (options) {
    const preserveRules = Boolean(options && options.preserveRules);

    if (!preserveRules) {
      HMTSTC_DATA.rules = {
        status: "locked",
        rules: [],
        filters: [],
        strategies: [],
        activation_log: []
      };
    } else {
      HMTSTC_DATA.rules = Object.assign({}, HMTSTC_DATA.rules || {}, {
        auth_state: "expired_preserved",
        auth_message: "Oturum süresi doldu; son başarılı rule listesi korunuyor."
      });
    }

    HMTSTC_DATA.ruleExamples = {};
    HMTSTC_DATA.usersPayload = { status: "locked", users: [] };
    HMTSTC_DATA.usersMessage = "";
  },

  handleUnauthorized: function () {
    const app = window.HMTSTC_APP || {};
    const state = app.state || {};

    localStorage.removeItem("hmtstc_user");
    localStorage.removeItem("hmtstc_token");
    localStorage.removeItem("hmtstc_role");
    localStorage.removeItem("hmtstc_force_password_change");

    this.clearRestrictedData({ preserveRules: true });

    state.auth = false;
    state.user = null;
    state.role = "user";
    state.forcePasswordChange = false;
    state.token = null;
    state.authRestorePending = false;
    state.authRestoreChecked = true;
    state.authRestoreError = "";
    state.page = "dashboard";
    state.apiReady = false;
    state.apiSyncReady = false;
    state.syncInProgress = false;
    state.heavySyncInProgress = false;
    state.loginError = "Oturum süresi doldu, tekrar giriş yap.";
    state.lastSyncBlockReason = "auth_401";
    state.authDiagnostics = Object.assign({}, state.authDiagnostics || {}, {
      tokenExists: false,
      authMeStatus: 401,
      lastRestoreAt: new Date().toLocaleTimeString("tr-TR"),
      lastBlockReason: "auth_401"
    });
    app.state = state;

    HMTSTC_DATA.systemStatus = Object.assign({}, HMTSTC_DATA.systemStatus || {}, {
      backend_api: "online",
      auth_status: "auth_expired",
      auth_message: "Oturum süresi doldu, tekrar giriş yap.",
      last_api_error_type: "http_401",
      last_api_error_message: "Oturum süresi doldu, tekrar giriş yap.",
      last_api_error_at: new Date().toLocaleTimeString("tr-TR")
    });

    if (app.render) app.render();
  },

  readErrorPayload: async function (response) {
    try {
      const payload = await response.json();

      if (payload && typeof payload === "object") {
        if (Array.isArray(payload.detail)) {
          return payload.detail.map(function (item) {
            return item.msg || item.message || JSON.stringify(item);
          }).join(" | ");
        }

        return payload.detail || payload.message || payload.error || response.statusText;
      }
    } catch (error) {
      try {
        return await response.text();
      } catch (ignored) {
        return response.statusText;
      }
    }

    return response.statusText;
  },

  fetchJson: async function (path, options) {
    let response;
    let timedOut = false;

    const requestKind = (options || {}).requestKind || this.API_REQUEST_KIND.CORE_READ;
    const preventGlobalAbort = Boolean((options || {}).preventGlobalAbort);
    const timeoutMs = Number((options || {}).timeoutMs || (requestKind === this.API_REQUEST_KIND.MUTATION ? 15000 : 10000));
    const controller = typeof AbortController !== "undefined" ? new AbortController() : null;
    const timer = controller ? setTimeout(function () {
      timedOut = true;
      controller.abort("hmtstc_request_timeout");
    }, timeoutMs) : null;

    try {
      const request = this.requestOptions(options);

      if (controller) {
        request.signal = controller.signal;
      }

      delete request.timeoutMs;
      delete request.requestKind;
      delete request.preventGlobalAbort;

      response = await fetch(this.getApiUrl(path), request);
    } catch (error) {
      const type = timedOut ? "timeout" : this.classifyApiError(error, null, path, requestKind);
      throw this.decorateApiError(error, type, error && error.message, path, 0, requestKind);
    } finally {
      if (timer) {
        clearTimeout(timer);
      }
    }

    if (response.status === 401) {
      this.handleUnauthorized();

      const authError = new Error("Oturum geçersiz.");
      throw this.decorateApiError(authError, "http_401", "Oturum geçersiz.", path, 401, requestKind);
    }

    if (!response.ok) {
      const detail = await this.readErrorPayload(response);
      const error = new Error(detail || ("HTTP " + response.status));

      error.status = response.status;
      error.detail = detail;
      throw this.decorateApiError(error, this.classifyApiError(error, response, path, requestKind), detail, path, response.status, requestKind);
    }

    try {
      const isCore = this.isCoreEndpoint(path) && requestKind === this.API_REQUEST_KIND.CORE_READ;
      const isHeavy = requestKind === this.API_REQUEST_KIND.HEAVY_READ;
      const isAudit = requestKind === this.API_REQUEST_KIND.AUDIT_BEST_EFFORT;
      HMTSTC_DATA.systemStatus = Object.assign({}, HMTSTC_DATA.systemStatus || {}, {
        backend_api: "online",
        last_api_ok_at: new Date().toLocaleTimeString("tr-TR"),
        last_api_request_kind: requestKind,
        core_failure_count: isCore ? 0 : Number((HMTSTC_DATA.systemStatus || {}).core_failure_count || 0),
        last_core_api_success_at: isCore ? new Date().toLocaleTimeString("tr-TR") : (HMTSTC_DATA.systemStatus || {}).last_core_api_success_at,
        heavy_status: isHeavy ? "ready" : (HMTSTC_DATA.systemStatus || {}).heavy_status,
        audit_status: isAudit ? "written" : (HMTSTC_DATA.systemStatus || {}).audit_status
      });
      return await response.json();
    } catch (error) {
      throw this.decorateApiError(error, "invalid_json", error && error.message, path, response.status, requestKind);
    }
  },

  renderAfterSync: function () {
    if (!HMTSTC_APP.state.auth || HMTSTC_APP.isUserEditing()) {
      return;
    }

    HMTSTC_APP.render();
  },

  normalizeUsersPayload: function (payload) {
    if (Array.isArray(payload)) {
      return {
        status: "ok",
        users: payload
      };
    }

    if (payload && typeof payload === "object") {
      return {
        status: payload.status || "ok",
        users: Array.isArray(payload.users) ? payload.users : [],
        message: payload.message || payload.detail || ""
      };
    }

    return {
      status: "ok",
      users: []
    };
  },

  isSafeRulesPayload: function (payload) {
    if (!payload || typeof payload !== "object") return false;

    const rules = Array.isArray(payload.rules) ? payload.rules : [];
    const filters = Array.isArray(payload.filters) ? payload.filters : [];
    const strategies = Array.isArray(payload.strategies) ? payload.strategies : [];
    const ruleStore = payload.rule_store_status || {};
    const activeTotal = Number(ruleStore.active_total_rules || ruleStore.total_rules || 0);
    const activePairCount = Number(ruleStore.active_filter_count || 0) + Number(ruleStore.active_strategy_count || 0);

    return rules.length > 0 ||
      filters.length > 0 ||
      strategies.length > 0 ||
      activeTotal > 0 ||
      activePairCount > 0 ||
      payload.status === "empty_rules";
  },

  preserveOrApplyRulesPayload: function (payload, source) {
    if (this.isSafeRulesPayload(payload)) {
      const previousRules = HMTSTC_DATA.rules || {};
      const previousSelection = (HMTSTC_APP.state && HMTSTC_APP.state.lastKnownRulesSelection) || {};
      const hasFilterSelection = Array.isArray(payload.selected_filter_ids);
      const hasStrategySelection = Array.isArray(payload.selected_strategy_ids);
      const nextPayload = Object.assign({}, payload);

      if (hasFilterSelection) {
        HMTSTC_APP.state.lastKnownRulesSelection = Object.assign({}, previousSelection, {
          filter: payload.selected_filter_ids.map(String)
        });
      } else if (Array.isArray(previousSelection.filter)) {
        nextPayload.selected_filter_ids = previousSelection.filter.slice();
      } else if (Array.isArray(previousRules.selected_filter_ids)) {
        nextPayload.selected_filter_ids = previousRules.selected_filter_ids.slice();
      }

      if (hasStrategySelection) {
        HMTSTC_APP.state.lastKnownRulesSelection = Object.assign({}, HMTSTC_APP.state.lastKnownRulesSelection || previousSelection, {
          strategy: payload.selected_strategy_ids.map(String)
        });
      } else if (Array.isArray(previousSelection.strategy)) {
        nextPayload.selected_strategy_ids = previousSelection.strategy.slice();
      } else if (Array.isArray(previousRules.selected_strategy_ids)) {
        nextPayload.selected_strategy_ids = previousRules.selected_strategy_ids.slice();
      }

      HMTSTC_DATA.rules = nextPayload;
      HMTSTC_DATA.systemStatus = Object.assign({}, HMTSTC_DATA.systemStatus || {}, {
        rules_payload_source: source || "api",
        rules_payload_preserved: false
      });
      return true;
    }

    HMTSTC_DATA.rules = Object.assign({}, HMTSTC_DATA.rules || {}, {
      preserved_after_empty_payload: true
    });
    HMTSTC_DATA.systemStatus = Object.assign({}, HMTSTC_DATA.systemStatus || {}, {
      rules_payload_source: source || "api",
      rules_payload_preserved: true,
      rules_payload_review_note: "Rules payload eksik veya guvensiz; son basarili rule listesi korundu."
    });
    return false;
  },

  clonePlainObject: function (value) {
    try {
      return JSON.parse(JSON.stringify(value || {}));
    } catch (error) {
      return {};
    }
  },

  sameJsonPayload: function (left, right) {
    function stable(value) {
      if (Array.isArray(value)) {
        return value.map(stable);
      }
      if (value && typeof value === "object") {
        return Object.keys(value).sort().reduce(function (acc, key) {
          acc[key] = stable(value[key]);
          return acc;
        }, {});
      }
      return value;
    }

    try {
      return JSON.stringify(stable(left || {})) === JSON.stringify(stable(right || {}));
    } catch (error) {
      try {
        return JSON.stringify(left || {}) === JSON.stringify(right || {});
      } catch (ignored) {
        return false;
      }
    }
  },

  applySettingsPayload: function (payload, source, options) {
    const incoming = payload && typeof payload === "object" ? this.clonePlainObject(payload) : {};
    const currentSettings = HMTSTC_DATA.settings || {};
    const state = HMTSTC_APP.state || {};
    const currentCoinFilter = currentSettings.coin_filter && typeof currentSettings.coin_filter === "object"
      ? currentSettings.coin_filter
      : {};
    const persistedCoinFilter = state.coinFilterPersistedCoinFilter && typeof state.coinFilterPersistedCoinFilter === "object"
      ? state.coinFilterPersistedCoinFilter
      : (((state.coinFilterLastSavedSnapshot || {}).coin_filter) || null);
    const expectedCoinFilter = (options && options.coinFilterExpected) || persistedCoinFilter;
    const hasIncomingCoinFilter = incoming.coin_filter && typeof incoming.coin_filter === "object" && Object.keys(incoming.coin_filter).length > 0;

    if (state.coinFilterDirty && state.coinFilterDraft) {
      const draftCoinFilter = (state.coinFilterDraft.coin_filter && typeof state.coinFilterDraft.coin_filter === "object")
        ? state.coinFilterDraft.coin_filter
        : {};
      incoming.coin_filter = this.clonePlainObject(draftCoinFilter);
      HMTSTC_DATA.systemStatus = Object.assign({}, HMTSTC_DATA.systemStatus || {}, {
        coin_filter_payload_source: source || "api",
        coin_filter_partial_payload_preserved: true,
        coin_filter_partial_payload_reason: "local_draft_preserved"
      });
    } else if (!hasIncomingCoinFilter && Object.keys(currentCoinFilter).length) {
      incoming.coin_filter = this.clonePlainObject(currentCoinFilter);
      HMTSTC_DATA.systemStatus = Object.assign({}, HMTSTC_DATA.systemStatus || {}, {
        coin_filter_payload_source: source || "api",
        coin_filter_partial_payload_preserved: true,
        coin_filter_partial_payload_reason: "partial_settings_payload"
      });
    } else if (expectedCoinFilter && hasIncomingCoinFilter && !this.sameJsonPayload(incoming.coin_filter, expectedCoinFilter)) {
      incoming.coin_filter = this.clonePlainObject(expectedCoinFilter);
      state.coinFilterBundleOverwriteGuarded = true;
      state.coinFilterSaveProof = Object.assign({}, state.coinFilterSaveProof || {}, {
        bundleOverwriteGuarded: true,
        bundleSource: source || "api",
        mismatchReason: "bundle_or_refresh_coin_filter_mismatch",
        persisted: true
      });
      HMTSTC_DATA.systemStatus = Object.assign({}, HMTSTC_DATA.systemStatus || {}, {
        coin_filter_payload_source: source || "api",
        coin_filter_bundle_overwrite_guarded: true,
        coin_filter_partial_payload_reason: "saved_value_preserved"
      });
    }

    if (!state.coinFilterDirty && incoming.coin_filter && typeof incoming.coin_filter === "object") {
      state.coinFilterDraft = this.clonePlainObject(incoming);
      state.coinFilterDraftSource = source || "backend_settings";
    }

    return incoming;
  },

  shouldFetchPaperLabStatus: function (force) {
    const state = HMTSTC_APP.state || {};

    if (state.paperLabStatusFetchInProgress) {
      return false;
    }

    if (force) {
      return true;
    }

    const lastFetchMs = Number(state.paperLabStatusLastFetchMs || 0);
    const minIntervalMs = Number(state.paperLabStatusMinIntervalMs || 60000);

    return !lastFetchMs || Date.now() - lastFetchMs >= minIntervalMs;
  },

  applyPaperLabStatusPayload: function (payload, source) {
    if (!payload || typeof payload !== "object") return false;

    const lastRun = payload.last_run && typeof payload.last_run === "object" ? payload.last_run : {};
    const directRun = lastRun.run_id ? lastRun : payload;
    const filterIds = Array.isArray(directRun.filter_ids)
      ? directRun.filter_ids
      : (Array.isArray(directRun.paper_lab_filter_ids) ? directRun.paper_lab_filter_ids : []);
    const strategyIds = Array.isArray(directRun.strategy_ids)
      ? directRun.strategy_ids
      : (Array.isArray(directRun.paper_lab_strategy_ids) ? directRun.paper_lab_strategy_ids : []);
    const completedAt = directRun.completed_at || payload.completed_at || payload.updated_at || new Date().toLocaleTimeString("tr-TR");
    const candidateCount = Number(directRun.candidate_count || directRun.paper_lab_candidate_count || payload.paper_lab_candidate_count || 0);
    const accepted = Number(directRun.accepted_combinations || payload.accepted_combinations || 0);
    const rejected = Number(directRun.rejected_combinations || payload.rejected_combinations || 0);
    const modelCount = Number(directRun.model_count || payload.model_count || 0);
    const summary = Object.assign({}, directRun, {
      status: directRun.status || payload.status || "ok",
      source: source || directRun.source || payload.source || "paper_lab_persistent_store",
      run_id: directRun.run_id || payload.run_id || "",
      updated_at: completedAt,
      completed_at: completedAt,
      selected_filter_count: Number(directRun.filter_count || filterIds.length || 0),
      selected_strategy_count: Number(directRun.strategy_count || strategyIds.length || 0),
      paper_lab_candidate_count: candidateCount,
      accepted_combinations: accepted,
      rejected_combinations: rejected,
      model_count: modelCount,
      rules_fingerprint: directRun.rules_fingerprint || payload.rules_fingerprint || "",
      last_run_matches_current_rules: Boolean(payload.last_run_matches_current_rules),
      store_persistent: payload.store_persistent !== false,
      message: directRun.error_message || payload.message || (directRun.run_id ? "Paper Lab kalıcı store'dan yüklendi." : "Paper Lab sonucu bekleniyor.")
    });

    HMTSTC_DATA.paperLabStatus = Object.assign({}, HMTSTC_DATA.paperLabStatus || {}, payload, summary, {
      last_run: lastRun,
      runs: Array.isArray(payload.runs) ? payload.runs : [],
      store_persistent: payload.store_persistent !== false,
      rules_fingerprint: payload.rules_fingerprint || summary.rules_fingerprint,
      last_run_matches_current_rules: Boolean(payload.last_run_matches_current_rules)
    });

    HMTSTC_APP.state.paperLabRun = Object.keys(lastRun).length ? lastRun : (summary.run_id ? summary : null);
    HMTSTC_APP.state.lastPaperLabResult = summary;
    HMTSTC_APP.state.paperLabRunId = summary.run_id || "";
    HMTSTC_APP.state.paperLabCandidateCount = candidateCount;
    HMTSTC_APP.state.paperLabModelCount = modelCount;
    HMTSTC_APP.state.paperLabAccepted = accepted;
    HMTSTC_APP.state.paperLabRejected = rejected;
    HMTSTC_APP.state.paperLabCompletedAt = completedAt;
    HMTSTC_APP.state.paperLabEngineStatus = summary.status === "failed" ? "failed" : (summary.run_id ? "completed" : HMTSTC_APP.state.paperLabEngineStatus);
    HMTSTC_APP.state.paperLabStatusLastFetchMs = Date.now();
    HMTSTC_APP.state.paperLabStatusLoading = false;

    return true;
  },

  fetchPaperLabStatus: async function (options) {
    const force = Boolean(options && options.force);
    const render = Boolean(options && options.render);
    const source = (options && options.source) || (force ? "paper_lab_force_refresh" : "paper_lab_status_throttled");

    if (!this.shouldFetchPaperLabStatus(force)) {
      return HMTSTC_DATA.paperLabStatus || null;
    }

    HMTSTC_APP.state.paperLabStatusFetchInProgress = true;
    HMTSTC_APP.state.paperLabStatusLoading = true;

    try {
      const payload = await this.fetchJson("/api/rules/paper-lab/status", {
        requestKind: this.API_REQUEST_KIND.CORE_READ,
        timeoutMs: 10000
      });
      this.applyPaperLabStatusPayload(payload, source);
      if (render) {
        this.renderAfterSync();
      }
      return payload;
    } catch (error) {
      HMTSTC_DATA.paperLabStatus = Object.assign({}, HMTSTC_DATA.paperLabStatus || {}, {
        status: (HMTSTC_DATA.paperLabStatus || {}).status || "loading",
        message: this.apiErrorMessage(error, "Paper Lab sonucu yüklenemedi."),
        status_load_error: true,
        updated_at: new Date().toLocaleTimeString("tr-TR")
      });
      return null;
    } finally {
      HMTSTC_APP.state.paperLabStatusLastFetchMs = Date.now();
      HMTSTC_APP.state.paperLabStatusFetchInProgress = false;
      HMTSTC_APP.state.paperLabStatusLoading = false;
    }
  },

  syncUsersData: async function () {
    const role = String(HMTSTC_APP.state.role || localStorage.getItem("hmtstc_role") || "user")
      .trim()
      .toLowerCase();

    if (!HMTSTC_APP.state.auth || role !== "owner") {
      HMTSTC_DATA.usersPayload = {
        status: "locked",
        users: []
      };

      HMTSTC_APP.state.usersLoaded = true;
      HMTSTC_APP.state.usersLoading = false;

      return HMTSTC_DATA.usersPayload;
    }

    try {
      const payload = await this.fetchJson("/api/users");

      HMTSTC_DATA.usersPayload = this.normalizeUsersPayload(payload);
      HMTSTC_APP.state.usersLoaded = true;
      HMTSTC_APP.state.usersLoading = false;

      return HMTSTC_DATA.usersPayload;
    } catch (error) {
      HMTSTC_APP.state.usersLoaded = true;
      HMTSTC_APP.state.usersLoading = false;

      HMTSTC_DATA.usersPayload = {
        status: "error",
        users: [],
        message: this.apiErrorMessage(error, "Kullanıcı listesi alınamadı.")
      };

      return HMTSTC_DATA.usersPayload;
    }
  },

  syncNow: async function () {
    HMTSTC_APP.state.syncInProgress = false;
    await this.syncApiData();
  },

  syncApiData: async function (options) {
    const skipHeavySync = Boolean(options && options.skipHeavySync);
    const skipPaperLabStatusFetch = Boolean(options && options.skipPaperLabStatusFetch);

    if (HMTSTC_APP.state.authRestorePending) {
      HMTSTC_APP.state.lastSyncBlockReason = "auth_restore_pending";
      HMTSTC_APP.state.authDiagnostics = Object.assign({}, HMTSTC_APP.state.authDiagnostics || {}, {
        tokenExists: Boolean(HMTSTC_APP.state.token || localStorage.getItem("hmtstc_token")),
        lastBlockReason: "auth_restore_pending"
      });
      return;
    }

    if (!HMTSTC_APP.state.auth) {
      const tokenExists = Boolean(HMTSTC_APP.state.token || localStorage.getItem("hmtstc_token"));
      HMTSTC_APP.state.lastSyncBlockReason = tokenExists ? "auth_not_verified" : "no_token";
      HMTSTC_APP.state.authDiagnostics = Object.assign({}, HMTSTC_APP.state.authDiagnostics || {}, {
        tokenExists: tokenExists,
        lastBlockReason: HMTSTC_APP.state.lastSyncBlockReason
      });
      return;
    }

    if (HMTSTC_APP.state.loginInProgress) {
      HMTSTC_APP.state.lastSyncBlockReason = "login_in_progress";
      return;
    }

    if (HMTSTC_APP.state.forcePasswordChange) {
      HMTSTC_APP.state.apiReady = false;
      HMTSTC_APP.state.apiSyncReady = false;
      HMTSTC_APP.state.lastSyncBlockReason = "force_password_change";
      return;
    }

    if (HMTSTC_APP.isUserEditing() || HMTSTC_APP.state.syncInProgress) {
      HMTSTC_APP.state.lastSyncBlockReason = HMTSTC_APP.state.syncInProgress ? "sync_in_progress" : "user_editing";
      return false;
    }

    if (HMTSTC_APP.state.apiBackoffUntil && Date.now() < HMTSTC_APP.state.apiBackoffUntil) {
      HMTSTC_APP.state.lastSyncBlockReason = "api_backoff";
      return false;
    }

    HMTSTC_APP.state.lastSyncBlockReason = "";
    HMTSTC_APP.state.syncInProgress = true;

    try {
      HMTSTC_APP.state.apiSyncReady = false;

      let bundled = null;
      let bundleError = null;

      try {
        bundled = await this.fetchJson("/api/dashboard/bundle", { requestKind: this.API_REQUEST_KIND.CORE_READ, timeoutMs: 10000 });
      } catch (error) {
        bundleError = error;
        bundled = null;
      }

      if (bundled && bundled.status === "ok") {
        if (bundled.build && bundled.build.label) {
          window.HMTSTC_BUILD_LABEL = bundled.build.label;
          HMTSTC_DATA.build = bundled.build;
          localStorage.setItem("hmtstc_build_label", bundled.build.label);
        }

        HMTSTC_DATA.dashboard = bundled.dashboard || {};
        HMTSTC_DATA.positions = Array.isArray(bundled.positions) ? bundled.positions : [];
        HMTSTC_DATA.history = Array.isArray(bundled.history) ? bundled.history : [];
        HMTSTC_DATA.logsPayload = bundled.logs || { status: "ok", logs: [] };
        HMTSTC_DATA.logs = Array.isArray(bundled.logs) ? bundled.logs : ((bundled.logs || {}).logs || []);
        HMTSTC_DATA.settings = this.applySettingsPayload(bundled.settings || {}, "dashboard_bundle", options);
        HMTSTC_DATA.botStatus = bundled.botStatus || {};
        if (bundled.botScan) {
          HMTSTC_DATA.botScan = bundled.botScan;
          HMTSTC_DATA.botScan.updated_at = bundled.botScan.time || bundled.botScan.scan_time || new Date().toLocaleTimeString("tr-TR");
          HMTSTC_DATA.scan_live = Boolean(bundled.botScan.live);
        }
        this.preserveOrApplyRulesPayload(bundled.rules, "dashboard_bundle");
        const bundlePaperLabApplied = this.applyPaperLabStatusPayload(bundled.paper_lab_status, "dashboard_bundle");

        if (bundled.users) {
          HMTSTC_DATA.usersPayload = HMTSTC_APP.normalizeUsersPayload(bundled.users);
          HMTSTC_APP.state.usersLoaded = true;
          HMTSTC_APP.state.usersLoading = false;
        }

        HMTSTC_APP.state.settingsLoaded = true;
        HMTSTC_APP.state.apiReady = true;
        HMTSTC_APP.state.apiSyncReady = true;
        HMTSTC_APP.state.apiBackoffUntil = null;
        HMTSTC_APP.state.lastSyncAt = new Date().toLocaleTimeString("tr-TR");
        HMTSTC_DATA.systemStatus = Object.assign({}, HMTSTC_DATA.systemStatus || {}, {
          bundle_status: "ok",
          backend_api: "online",
          last_api_error_type: "",
          last_api_error_message: "",
          core_failure_count: 0,
          last_api_ok_at: new Date().toLocaleTimeString("tr-TR")
        });

        this.renderAfterSync();
        if (!bundlePaperLabApplied && !skipPaperLabStatusFetch) {
          this.fetchPaperLabStatus({ force: false, render: true, source: "bundle_missing_throttled" });
        }
        if (!skipHeavySync) {
          this.syncHeavyApiData();
        }

        return;
      }

      const results = await Promise.allSettled([
        this.fetchJson("/api/dashboard", { requestKind: this.API_REQUEST_KIND.CORE_READ }),
        this.fetchJson("/api/positions", { requestKind: this.API_REQUEST_KIND.CORE_READ }),
        this.fetchJson("/api/history", { requestKind: this.API_REQUEST_KIND.CORE_READ }),
        this.fetchJson("/api/logs", { requestKind: this.API_REQUEST_KIND.CORE_READ }),
        this.fetchJson("/api/settings", { requestKind: this.API_REQUEST_KIND.CORE_READ }),
        this.fetchJson("/api/bot/status", { requestKind: this.API_REQUEST_KIND.CORE_READ }),
        this.fetchJson("/api/rules", { requestKind: this.API_REQUEST_KIND.CORE_READ })
      ]);

      const keys = [
        "dashboard",
        "positions",
        "history",
        "logs",
        "settings",
        "botStatus",
        "rules"
      ];

      results.forEach(function (result, index) {
        if (result.status !== "fulfilled") return;

        const key = keys[index];

        if (key === "positions") {
          HMTSTC_DATA.positions = Array.isArray(result.value) ? result.value : [];
        } else if (key === "history") {
          HMTSTC_DATA.history = Array.isArray(result.value) ? result.value : [];
        } else if (key === "logs") {
          HMTSTC_DATA.logsPayload = result.value;
          HMTSTC_DATA.logs = Array.isArray(result.value) ? result.value : (result.value.logs || []);
        } else if (key === "settings") {
          const newSettings = HMTSTC_APP.applySettingsPayload(result.value, "api_settings", options);
          const currentSettings = HMTSTC_DATA.settings || {};

          if (HMTSTC_APP.state.strategyDirty || HMTSTC_APP.state.strategySaving) {
            newSettings.strategies = currentSettings.strategies || newSettings.strategies || [];
            newSettings.current_strategy = currentSettings.current_strategy || newSettings.current_strategy || "";
          }

          HMTSTC_DATA.settings = newSettings;
          HMTSTC_APP.state.settingsLoaded = true;
        } else if (key === "rules") {
          HMTSTC_APP.preserveOrApplyRulesPayload(result.value, "api_rules");
        } else {
          HMTSTC_DATA[key] = result.value;
        }
      });

      const criticalReady = results.every(function (result) {
        return result.status === "fulfilled";
      });
      const fallbackCoreReady = results[4].status === "fulfilled" && results[6].status === "fulfilled";

      HMTSTC_APP.state.apiReady = fallbackCoreReady || criticalReady;
      HMTSTC_APP.state.apiSyncReady = fallbackCoreReady || criticalReady;
      HMTSTC_APP.state.lastSyncAt = new Date().toLocaleTimeString("tr-TR");
      HMTSTC_DATA.systemStatus = Object.assign({}, HMTSTC_DATA.systemStatus || {}, {
        bundle_status: bundleError ? "degraded" : "fallback",
        bundle_message: bundleError ? this.apiErrorMessage(bundleError, "Dashboard bundle fallback kullanıldı.") : "Dashboard bundle fallback kullanıldı."
      });

      this.renderAfterSync();
      if (!skipPaperLabStatusFetch) {
        this.fetchPaperLabStatus({ force: false, render: true, source: "api_rules_paper_lab_status_throttled" });
      }
      if (!skipHeavySync) {
        this.syncHeavyApiData();
      }
    } catch (error) {
      HMTSTC_APP.state.apiReady = false;
      HMTSTC_APP.state.apiSyncReady = false;

      if (!error || error.status === 0 || error.status >= 500) {
        HMTSTC_APP.state.apiBackoffUntil = Date.now() + 30000;
      }

      console.error("HMTSTC API sync hatası:", error);

      this.renderAfterSync();
    } finally {
      HMTSTC_APP.state.syncInProgress = false;
    }
  },

  syncHeavyApiData: async function () {
    if (!HMTSTC_APP.state.auth || HMTSTC_APP.state.forcePasswordChange) {
      return;
    }

    if (HMTSTC_APP.state.heavySyncInProgress) {
      return;
    }

    const nowMs = Date.now();

    if (!HMTSTC_APP.state.heavySyncAllowedAtMs) {
      HMTSTC_APP.state.heavySyncAllowedAtMs = nowMs + 120000;
      HMTSTC_DATA.systemStatus = Object.assign({}, HMTSTC_DATA.systemStatus || {}, {
        heavy_status: "deferred",
        heavy_message: "Canlı başlangıç için ağır analiz ertelendi."
      });
      return;
    }

    if (nowMs < HMTSTC_APP.state.heavySyncAllowedAtMs) {
      return;
    }

    if (HMTSTC_APP.state.lastHeavySyncMs && nowMs - HMTSTC_APP.state.lastHeavySyncMs < 300000) {
      return;
    }

    try {
      HMTSTC_APP.state.heavySyncInProgress = true;
      HMTSTC_APP.state.lastHeavySyncMs = nowMs;
      HMTSTC_DATA.systemStatus = Object.assign({}, HMTSTC_DATA.systemStatus || {}, {
        heavy_status: "syncing"
      });

      const today = new Date();
      const prior = new Date();

      prior.setDate(today.getDate() - 30);

      const performanceStart = HMTSTC_APP.state.performanceStart || prior.toISOString().slice(0, 10);
      const performanceEnd = HMTSTC_APP.state.performanceEnd || today.toISOString().slice(0, 10);

      const role = String(HMTSTC_APP.state.role || localStorage.getItem("hmtstc_role") || "user")
        .trim()
        .toLowerCase();

      const canUseRuleExamples = role === "owner" || role === "admin";
      const canUseOwner = role === "owner";

      const requests = [
        {
          key: "botScan",
          promise: this.fetchJson("/api/bot/last-scan", { requestKind: this.API_REQUEST_KIND.HEAVY_READ, timeoutMs: 12000 })
        },
        {
          key: "performance",
          promise: this.fetchJson("/api/performance?start=" + performanceStart + "&end=" + performanceEnd, { requestKind: this.API_REQUEST_KIND.HEAVY_READ, timeoutMs: 12000 })
        },
        {
          key: "me",
          promise: this.fetchJson("/api/auth/me", { requestKind: this.API_REQUEST_KIND.CORE_READ })
        },
        {
          key: "reports",
          promise: this.fetchJson("/api/models/reports?period=7d", { requestKind: this.API_REQUEST_KIND.HEAVY_READ, timeoutMs: 12000 })
        },
        {
          key: "audit",
          promise: this.fetchJson("/api/audit?limit=80", { requestKind: this.API_REQUEST_KIND.AUDIT_BEST_EFFORT, timeoutMs: 8000 })
        },
        {
          key: "intelligence",
          promise: this.fetchJson("/api/intelligence/overview", { requestKind: this.API_REQUEST_KIND.HEAVY_READ, timeoutMs: 12000 })
        },
        {
          key: "autoBotModeDecision61",
          promise: this.fetchJson("/api/intelligence/auto-bot-mode-decision", { requestKind: this.API_REQUEST_KIND.HEAVY_READ, timeoutMs: 12000 })
        },
        {
          key: "tradeabilityDecision60",
          promise: this.fetchJson("/api/intelligence/tradeability-decision", { requestKind: this.API_REQUEST_KIND.HEAVY_READ, timeoutMs: 12000 })
        },
        {
          key: "meApiConnection67",
          promise: this.fetchJson("/api/users/me/api-connection", { requestKind: this.API_REQUEST_KIND.HEAVY_READ, timeoutMs: 12000 })
        }
      ];

      if (canUseRuleExamples && !HMTSTC_DATA.ruleExamples) {
        requests.push({
          key: "ruleExamples",
          promise: this.fetchJson("/api/rules/examples", { requestKind: this.API_REQUEST_KIND.HEAVY_READ, timeoutMs: 12000 })
        });
      }

      if (canUseOwner) {
        requests.push({
          key: "users",
          promise: this.fetchJson("/api/users", { requestKind: this.API_REQUEST_KIND.HEAVY_READ, timeoutMs: 12000 })
        });
      } else {
        HMTSTC_DATA.usersPayload = {
          status: "locked",
          users: []
        };
      }

      const results = await Promise.allSettled(requests.map(function (item) {
        return item.promise;
      }));

      requests.forEach(function (request, index) {
        const result = results[index];

        if (result.status !== "fulfilled") {
          if (result.reason && result.reason.apiErrorType === "timeout") {
            HMTSTC_DATA.systemStatus = Object.assign({}, HMTSTC_DATA.systemStatus || {}, {
              heavy_status: "timeout",
              heavy_message: result.reason.userMessage || "Ağır analiz isteği zaman aşımına uğradı."
            });
          }
          return;
        }

        if (request.key === "binanceMarket") {
          HMTSTC_DATA.binanceMarket = result.value;
          HMTSTC_DATA.binanceMarket.updated_at = new Date().toLocaleTimeString("tr-TR");
        } else if (request.key === "botScan") {
          HMTSTC_DATA.botScan = result.value;
          HMTSTC_DATA.botScan.updated_at = HMTSTC_DATA.botScan.time || new Date().toLocaleTimeString("tr-TR");
          HMTSTC_DATA.scan_live = Boolean(HMTSTC_DATA.botScan.live);
        } else if (request.key === "me") {
          HMTSTC_DATA.me = result.value;
          HMTSTC_APP.state.role = result.value.role || HMTSTC_APP.state.role || "user";
          HMTSTC_APP.state.forcePasswordChange = Boolean(result.value.force_password_change);

          localStorage.setItem("hmtstc_role", HMTSTC_APP.state.role);
          localStorage.setItem("hmtstc_force_password_change", HMTSTC_APP.state.forcePasswordChange ? "true" : "false");
        } else if (request.key === "users") {
          HMTSTC_DATA.usersPayload = HMTSTC_APP.normalizeUsersPayload(result.value);
          HMTSTC_APP.state.usersLoaded = true;
          HMTSTC_APP.state.usersLoading = false;
        } else {
          HMTSTC_DATA[request.key] = result.value;
        }
      });

      HMTSTC_DATA.systemStatus = Object.assign({}, HMTSTC_DATA.systemStatus || {}, {
        heavy_status: (HMTSTC_DATA.systemStatus || {}).heavy_status === "timeout" ? "timeout" : "ready"
      });
      this.renderAfterSync();
    } catch (error) {
      HMTSTC_DATA.scan_live = false;
      HMTSTC_DATA.systemStatus = Object.assign({}, HMTSTC_DATA.systemStatus || {}, {
        heavy_status: "degraded",
        heavy_message: this.apiErrorMessage(error, "Ağır analiz yenilenemedi.")
      });

      console.error("HMTSTC API sync hatası:", error);

      this.renderAfterSync();
    } finally {
      HMTSTC_APP.state.heavySyncInProgress = false;
    }
  }
};
