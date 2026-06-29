window.HMTSTC_APP_RULES = {
  strategyRuntimeSummary: function (payload) {
    const runtime = payload && typeof payload === "object" ? payload : {};
    return {
      contract: runtime.contract || "strategy_runtime_v1",
      active_strategy_ids: this.normalizeIdList(runtime.active_strategy_ids || []),
      passed: Number(runtime.passed || 0),
      blocked: runtime.status === "blocked",
      reason: runtime.reason || null,
      paper_lab_isolated: runtime.paper_lab_isolated === true
    };
  },

  getRuleDraft: function (type) {
    const key = type === "strategy" ? "strategyRuleDraft" : "filterRuleDraft";

    if (this.state[key] === undefined || this.state[key] === null) {
      this.state[key] = "";
    }

    return this.state[key];
  },

  setRuleDraft: function (type, value) {
    const key = type === "strategy" ? "strategyRuleDraft" : "filterRuleDraft";
    this.state[key] = value;
    this.state.ruleEditorDirty = true;
  },

  normalizeIdList: function (list) {
    const seen = {};

    return (Array.isArray(list) ? list : [])
      .map(function (item) {
        return String(item || "").trim();
      })
      .filter(function (item) {
        if (!item || seen[item]) return false;
        seen[item] = true;
        return true;
      })
      .sort();
  },

  sameIdSet: function (a, b) {
    const left = this.normalizeIdList(a);
    const right = this.normalizeIdList(b);

    if (left.length !== right.length) return false;

    return left.every(function (item, index) {
      return item === right[index];
    });
  },

  setRulesSelectionProof: function (stage, payloadFilters, payloadStrategies, extra) {
    const details = extra && typeof extra === "object" ? extra : {};
    const rendered = this.state.dashboardRenderedRuleSelection || {};
    const payloadFilterIds = this.normalizeIdList(payloadFilters);
    const payloadStrategyIds = this.normalizeIdList(payloadStrategies);
    const backendFilterIds = this.normalizeIdList(details.backend_filter_ids || payloadFilterIds);
    const backendStrategyIds = this.normalizeIdList(details.backend_strategy_ids || payloadStrategyIds);
    const renderFilterIds = this.normalizeIdList(details.render_filter_ids || rendered.filter || []);
    const renderStrategyIds = this.normalizeIdList(details.render_strategy_ids || rendered.strategy || []);
    const paperLabFilterIds = this.normalizeIdList(details.paper_lab_filter_ids || backendFilterIds);
    const paperLabStrategyIds = this.normalizeIdList(details.paper_lab_strategy_ids || backendStrategyIds);
    const proof = Object.assign({}, details, {
      stage: stage,
      updated_at: new Date().toLocaleTimeString("tr-TR"),
      beforeSaveFilterIds: this.normalizeIdList(details.beforeSaveFilterIds || details.before_save_filter_ids || payloadFilterIds),
      beforeSaveStrategyIds: this.normalizeIdList(details.beforeSaveStrategyIds || details.before_save_strategy_ids || payloadStrategyIds),
      payloadFilterIds: payloadFilterIds,
      payloadStrategyIds: payloadStrategyIds,
      responseFilterIds: backendFilterIds,
      responseStrategyIds: backendStrategyIds,
      refreshFilterIds: this.normalizeIdList(details.refreshFilterIds || details.refresh_filter_ids || backendFilterIds),
      refreshStrategyIds: this.normalizeIdList(details.refreshStrategyIds || details.refresh_strategy_ids || backendStrategyIds),
      renderFilterIds: renderFilterIds,
      renderStrategyIds: renderStrategyIds,
      afterPaperLabFilterIds: this.normalizeIdList(details.afterPaperLabFilterIds || details.after_paper_lab_filter_ids || renderFilterIds),
      afterPaperLabStrategyIds: this.normalizeIdList(details.afterPaperLabStrategyIds || details.after_paper_lab_strategy_ids || renderStrategyIds),
      payload_filter_ids: payloadFilterIds,
      payload_strategy_ids: payloadStrategyIds,
      backend_filter_ids: backendFilterIds,
      backend_strategy_ids: backendStrategyIds,
      render_filter_ids: renderFilterIds,
      render_strategy_ids: renderStrategyIds,
      paper_lab_filter_ids: paperLabFilterIds,
      paper_lab_strategy_ids: paperLabStrategyIds,
      mismatch: Boolean(details.mismatch),
      mismatchStage: details.mismatchStage || details.mismatch_stage || "",
      backend_filter_matches_payload: this.sameIdSet(payloadFilterIds, backendFilterIds),
      backend_strategy_matches_payload: this.sameIdSet(payloadStrategyIds, backendStrategyIds),
      render_filter_matches_payload: this.sameIdSet(payloadFilterIds, renderFilterIds),
      render_strategy_matches_payload: this.sameIdSet(payloadStrategyIds, renderStrategyIds),
      paper_lab_filter_matches_payload: this.sameIdSet(payloadFilterIds, paperLabFilterIds),
      paper_lab_strategy_matches_payload: this.sameIdSet(payloadStrategyIds, paperLabStrategyIds)
    });

    this.state.rulesSelectionProof = proof;
    this.state.rulesSelectionProofHistory = (Array.isArray(this.state.rulesSelectionProofHistory)
      ? this.state.rulesSelectionProofHistory
      : []
    ).concat([proof]).slice(-10);

    return proof;
  },

  dashboardActiveSelectionSnapshot: function () {
    const draft = this.state.dashboardRuleSelectionDraft || {};
    const rules = HMTSTC_DATA.rules || {};
    const lastKnown = this.state.lastKnownRulesSelection || {};
    const filterIds = Array.isArray(draft.filter)
      ? draft.filter
      : (Array.isArray(rules.selected_filter_ids)
        ? rules.selected_filter_ids
        : (Array.isArray(lastKnown.filter) ? lastKnown.filter : []));
    const strategyIds = Array.isArray(draft.strategy)
      ? draft.strategy
      : (Array.isArray(rules.selected_strategy_ids)
        ? rules.selected_strategy_ids
        : (Array.isArray(lastKnown.strategy) ? lastKnown.strategy : []));

    return {
      filter: this.normalizeIdList(filterIds),
      strategy: this.normalizeIdList(strategyIds)
    };
  },

  activeRuleIds: function (source) {
    return Array.isArray(source)
      ? source.map(function (item) {
          if (!item || item.enabled === false || item.active === false) return "";
          return String(item.id || item.name || "").trim();
        }).filter(Boolean)
      : [];
  },

  updateDashboardRuleDraft: function (kind, id, checked) {
    const cleanKind = kind === "strategy" ? "strategy" : "filter";
    const rules = HMTSTC_DATA.rules || {};
    const selectedKey = cleanKind === "strategy" ? "selected_strategy_ids" : "selected_filter_ids";
    const draftKey = cleanKind;
    const lastKnownSelection = this.state.lastKnownRulesSelection || {};

    this.state.dashboardRuleSelectionDraft = this.state.dashboardRuleSelectionDraft || {};

    let current = Array.isArray(this.state.dashboardRuleSelectionDraft[draftKey])
      ? this.state.dashboardRuleSelectionDraft[draftKey].map(String)
      : null;

    if (!current) {
      current = Array.isArray(rules[selectedKey])
        ? rules[selectedKey].map(String)
        : (Array.isArray(lastKnownSelection[draftKey]) ? lastKnownSelection[draftKey].map(String) : []);
    }

    const cleanId = String(id || "").trim();
    const next = current.filter(function (item) { return item !== cleanId; });

    if (checked && cleanId) {
      next.push(cleanId);
    }

    this.state.dashboardRuleSelectionDraft[draftKey] = next;
  },



  newRuleDraft: function (type) {
    const cleanType = type === "strategy" ? "strategy" : "filter";
    const key = cleanType === "strategy" ? "strategyRuleDraft" : "filterRuleDraft";

    this.state[key] = "";
    this.state.ruleEditorTab = cleanType;
    this.state.ruleEditorMode = "new";
    this.state.ruleEditorActiveId = "";
    this.state.ruleEditorDirty = false;

    HMTSTC_DATA.ruleValidation = null;

    this.pushRuleLog("YENİ: Boş " + (cleanType === "strategy" ? "strateji" : "filtre") + " editörü açıldı.");
  },

  newSimpleRuleDraft: function () {
    const selector = document.getElementById("simple-rule-type");
    const type = selector && selector.value === "strategy" ? "strategy" : "filter";
    this.newRuleDraft(type);
    this.render();
  },

  switchSimpleRuleType: function (type) {
    const cleanType = type === "strategy" ? "strategy" : "filter";

    this.state.ruleEditorTab = cleanType;

    if (this.state.ruleEditorMode === "new" && !this.state.ruleEditorDirty) {
      this.newRuleDraft(cleanType);
      return;
    }

    this.render();
  },

  simpleRuleId: function (type, name) {
    const prefix = type === "strategy" ? "USER_STRATEGY_" : "USER_FILTER_";

    const clean = String(name || type || "rule")
      .trim()
      .toUpperCase()
      .replace(/[^A-Z0-9_]+/g, "_")
      .replace(/^_+|_+$/g, "");

    return prefix + (clean || String(Date.now()));
  },

  normalizeRuleForSave: function (rule, type) {
    const cleanType = type === "strategy" ? "strategy" : "filter";
    const normalized = Object.assign({}, rule || {});

    normalized.type = cleanType;
    normalized.name = String(normalized.name || "").trim() || (cleanType === "strategy" ? "Yeni Strateji" : "Yeni Filtre");
    normalized.id = String(normalized.id || "").trim() || this.simpleRuleId(cleanType, normalized.name);
    normalized.version = Math.max(1, Number(normalized.version || 1));
    normalized.enabled = normalized.enabled === false ? false : true;

    normalized.description = String(normalized.description || "");
    normalized.risk_level = normalized.risk_level || "medium";
    normalized.required_metrics = Array.isArray(normalized.required_metrics) ? normalized.required_metrics : [];
    normalized.conditions = Array.isArray(normalized.conditions) ? normalized.conditions : [];
    normalized.avoid_conditions = Array.isArray(normalized.avoid_conditions) ? normalized.avoid_conditions : [];
    normalized.metadata = normalized.metadata && typeof normalized.metadata === "object"
      ? normalized.metadata
      : { source: "simple_rule_editor" };

    if (cleanType === "strategy") {
      normalized.strategy_type = normalized.strategy_type || "custom";
      normalized.entry_rules = Array.isArray(normalized.entry_rules) ? normalized.entry_rules : [];
      normalized.exit_rules = Array.isArray(normalized.exit_rules) ? normalized.exit_rules : [];

      delete normalized.min_score;
      delete normalized.compatible_strategy_types;
      delete normalized.score_rules;
    } else {
      const minScore = Number(normalized.min_score || 65);

      normalized.min_score = Number.isFinite(minScore) ? minScore : 65;
      normalized.compatible_strategy_types = Array.isArray(normalized.compatible_strategy_types)
        ? normalized.compatible_strategy_types
        : ["trend", "pullback", "momentum", "custom"];
      normalized.score_rules = Array.isArray(normalized.score_rules) ? normalized.score_rules : [];

      delete normalized.strategy_type;
      delete normalized.entry_rules;
      delete normalized.exit_rules;
    }

    return normalized;
  },

  validateRuleBeforeSave: function (rule, type) {
    const cleanType = type === "strategy" ? "strategy" : "filter";
    const errors = [];

    if (!rule || typeof rule !== "object" || Array.isArray(rule)) {
      errors.push("JSON object olmalı.");
    }

    if (rule && rule.type && rule.type !== cleanType) {
      errors.push("Seçilen tip ile JSON içindeki type aynı olmalı.");
    }

    if (rule && !String(rule.name || "").trim()) {
      errors.push("name alanı zorunlu.");
    }

    if (errors.length) {
      this.pushRuleLog("HATA: " + errors.join(" | "));
      return false;
    }

    return true;
  },

  refreshRulesData: async function () {
    try {
      const result = await this.fetchJson("/api/rules", {
        requestKind: "core_read",
        timeoutMs: 10000
      });

      if (this.preserveOrApplyRulesPayload) {
        this.preserveOrApplyRulesPayload(result, "rules_refresh");
      } else {
        HMTSTC_DATA.rules = result || {
          status: "ok",
          rules: [],
          filters: [],
          strategies: [],
          activation_log: []
        };
      }

      this.render();
      return true;
    } catch (error) {
      if (error && error.status === 401) {
        this.state.dashboardRuleSelectionSaving = false;
        this.pushRuleLog("UYARI: Oturum süresi doldu; son başarılı filtre/strateji listesi korunuyor.");
      } else {
        this.pushRuleLog("UYARI: Rule listesi yenilenemedi - " + this.apiErrorMessage(error, "Backend erişilemiyor."));
      }
      return false;
    }
  },

  updateLocalRulesCache: function (rule, action) {
    if (!rule || !rule.id) return;

    const payload = HMTSTC_DATA.rules && typeof HMTSTC_DATA.rules === "object"
      ? HMTSTC_DATA.rules
      : { status: "ok", rules: [], filters: [], strategies: [], activation_log: [] };

    const currentRules = Array.isArray(payload.rules) ? payload.rules.slice() : [];
    const nextRules = currentRules.filter(function (item) {
      return item && item.id !== rule.id;
    });

    if (action !== "delete") {
      nextRules.push(rule);
    }

    payload.rules = nextRules;
    payload.filters = nextRules.filter(function (item) {
      return item && item.type === "filter";
    });
    payload.strategies = nextRules.filter(function (item) {
      return item && item.type === "strategy";
    });

    HMTSTC_DATA.rules = payload;
  },

  openRuleInEditor: function (rule) {
    if (!rule || !rule.id || !rule.type) {
      this.pushRuleLog("HATA: Açılacak rule geçersiz.");
      return false;
    }

    const type = rule.type === "strategy" ? "strategy" : "filter";
    const key = type === "strategy" ? "strategyRuleDraft" : "filterRuleDraft";

    this.state[key] = JSON.stringify(rule, null, 2);
    this.state.ruleEditorTab = type;
    this.state.ruleEditorMode = "edit";
    this.state.ruleEditorActiveId = rule.id;
    this.state.ruleEditorDirty = false;

    HMTSTC_DATA.ruleValidation = null;

    this.render();
    return true;
  },

  loadRuleToEditor: async function (ruleId) {
    if (!ruleId) return;

    const localRules = ((HMTSTC_DATA.rules || {}).rules || []);
    const localRule = localRules.find(function (item) {
      return item && item.id === ruleId;
    });

    this.pushRuleLog("YÜKLENİYOR: " + ruleId);

    try {
      const result = await this.fetchJson("/api/rules/get", {
        method: "POST",
        requestKind: "mutation",
        preventGlobalAbort: true,
        timeoutMs: 15000,
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ rule_id: ruleId })
      });

      if (!this.openRuleInEditor(result.rule)) {
        throw new Error("Backend rule payload boş döndü.");
      }

      this.pushRuleLog("DÜZELT: " + ruleId + " editöre yüklendi.");
    } catch (error) {
      if (localRule && this.openRuleInEditor(localRule)) {
        this.pushRuleLog("DÜZELT: " + ruleId + " local listeden editöre yüklendi.");
        return;
      }

      this.pushRuleLog("HATA: " + this.apiErrorMessage(error, "Rule editöre yüklenemedi."));
      this.render();
    }
  },

  saveSimpleRuleDraft: async function () {
    const selector = document.getElementById("simple-rule-type");
    const type = selector && selector.value === "strategy" ? "strategy" : "filter";
    const key = type === "strategy" ? "strategyRuleDraft" : "filterRuleDraft";

    const editor = document.querySelector(".simple-rule-code-editor");
    const text = editor ? editor.value : this.getRuleDraft(type);

    let rule;

    try {
      rule = JSON.parse(text);
    } catch (error) {
      this.pushRuleLog("HATA: JSON okunamadı - " + error.message);
      return;
    }

    if (!this.validateRuleBeforeSave(rule, type)) return;

    rule = this.normalizeRuleForSave(rule, type);
    this.state[key] = JSON.stringify(rule, null, 2);

    await this.saveRuleDraft(type, rule);
  },

  saveRuleDraft: async function (type, preparedRule) {
    const cleanType = type === "strategy" ? "strategy" : "filter";
    let rule = preparedRule;

    if (!rule) {
      try {
        rule = JSON.parse(this.getRuleDraft(cleanType));
      } catch (error) {
        this.pushRuleLog("HATA: JSON okunamadı - " + error.message);
        return;
      }

      if (!this.validateRuleBeforeSave(rule, cleanType)) return;
      rule = this.normalizeRuleForSave(rule, cleanType);
    }

    const previousRules = (((HMTSTC_DATA.rules || {}).rules || []).slice());
    const previousRule = previousRules.find(function (item) {
      return item && item.id === rule.id;
    });

    this.updateLocalRulesCache(rule, "save");
    this.state.ruleEditorActiveId = rule.id;
    this.state.ruleEditorMode = "edit";
    this.state.ruleEditorDirty = false;

    this.pushRuleLog("KAYDEDİLİYOR: " + rule.id);
    this.render();

    try {
      const result = await this.fetchJson("/api/rules/save", {
        method: "POST",
        requestKind: "mutation",
        preventGlobalAbort: true,
        timeoutMs: 15000,
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ rule: rule })
      });

      const saved = result.saved || rule;

      this.updateLocalRulesCache(saved, "save");
      this.state.ruleEditorActiveId = saved.id || rule.id;
      this.state.ruleEditorMode = "edit";
      this.state.ruleEditorDirty = false;

      this.pushRuleLog("KAYIT: " + (saved.id || rule.id) + (result.created ? " oluşturuldu." : " güncellendi."));

      if (this.auditAction) {
        try {
          await this.auditAction("rule_save", "ok", saved.id || rule.id, {
            type: cleanType,
            created: !!result.created
          });
        } catch (auditError) {
          this.pushRuleLog("UYARI: Rule save audit yazılamadı; kayıt başarılı kabul edildi.");
        }
      }

      await this.refreshRulesData();
    } catch (error) {
      if (previousRule) {
        this.updateLocalRulesCache(previousRule, "save");
      } else {
        this.updateLocalRulesCache(rule, "delete");
      }

      if (error && error.apiErrorType === "request_aborted") {
        this.pushRuleLog("HATA: İstek iptal edildi; tekrar dene. Rule taslağı korunuyor.");
      } else {
        this.pushRuleLog("HATA: " + this.apiErrorMessage(error, "Rule kaydedilemedi."));
      }

      if (this.auditAction) {
        try {
          await this.auditAction("rule_save", "error", rule.id || cleanType, {
            type: cleanType
          });
        } catch (auditError) {
          this.pushRuleLog("UYARI: Rule save hata audit kaydı yazılamadı.");
        }
      }

      this.render();
    }
  },

  deleteRule: async function (ruleId) {
    if (!ruleId) return;

    if (!confirm(ruleId + " silinsin mi?")) return;

    const previousRule = (((HMTSTC_DATA.rules || {}).rules || []).slice()).find(function (item) {
      return item && item.id === ruleId;
    });

    this.updateLocalRulesCache({ id: ruleId }, "delete");
    this.pushRuleLog("SİLİNİYOR: " + ruleId);
    this.render();

    try {
      try {
        await this.fetchJson("/api/rules/delete", {
          method: "POST",
          requestKind: "mutation",
          preventGlobalAbort: true,
          timeoutMs: 15000,
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ rule_id: ruleId })
        });
      } catch (postError) {
        if (postError && (postError.status === 404 || postError.status === 405)) {
          await this.fetchJson("/api/rules/" + encodeURIComponent(ruleId), {
            method: "DELETE",
            requestKind: "mutation",
            preventGlobalAbort: true,
            timeoutMs: 15000
          });
        } else {
          throw postError;
        }
      }

      this.pushRuleLog("SİLİNDİ: " + ruleId);

      if (this.auditAction) {
        try {
          await this.auditAction("rule_delete", "ok", ruleId, { rule_id: ruleId });
        } catch (auditError) {
          this.pushRuleLog("UYARI: Rule delete audit yazılamadı; silme başarılı kabul edildi.");
        }
      }

      await this.refreshRulesData();
    } catch (error) {
      if (previousRule) {
        this.updateLocalRulesCache(previousRule, "save");
      }

      if (error && error.apiErrorType === "request_aborted") {
        this.pushRuleLog("HATA: İstek iptal edildi; tekrar dene. Rule listesi korunuyor.");
      } else {
        this.pushRuleLog("HATA: " + this.apiErrorMessage(error, "Rule silinemedi."));
      }

      if (this.auditAction) {
        try {
          await this.auditAction("rule_delete", "error", ruleId, { rule_id: ruleId });
        } catch (auditError) {
          this.pushRuleLog("UYARI: Rule delete hata audit kaydı yazılamadı.");
        }
      }

      this.render();
    }
  },

  saveDashboardRuleSelection: async function () {
    if (this.state.dashboardRuleSelectionSaving) {
      this.pushRuleLog("UYARI: Seçim kaydı zaten devam ediyor.");
      return;
    }

    const beforeSave = this.dashboardActiveSelectionSnapshot();
    const selectionSnapshot = {
      filter: beforeSave.filter.slice(),
      strategy: beforeSave.strategy.slice()
    };

    this.state.dashboardRuleSelectionSaving = true;
    this.state.dashboardRuleSelectionDraft = {
      filter: selectionSnapshot.filter.slice(),
      strategy: selectionSnapshot.strategy.slice()
    };
    this.setRulesSelectionProof("save_payload", selectionSnapshot.filter, selectionSnapshot.strategy, {
      beforeSaveFilterIds: beforeSave.filter.slice(),
      beforeSaveStrategyIds: beforeSave.strategy.slice(),
      save_payload_filter_ids: selectionSnapshot.filter.slice(),
      save_payload_strategy_ids: selectionSnapshot.strategy.slice()
    });

    this.pushRuleLog(
      "SEÇİM: " +
      selectionSnapshot.filter.length +
      " filtre / " +
      selectionSnapshot.strategy.length +
      " strateji kaydediliyor."
    );

    try {
      const result = await this.fetchJson("/api/rules/selection", {
        method: "POST",
        requestKind: "mutation",
        preventGlobalAbort: true,
        timeoutMs: 15000,
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          selected_filter_ids: selectionSnapshot.filter,
          selected_strategy_ids: selectionSnapshot.strategy
        })
      });

      const resultFilters = this.normalizeIdList(result.selected_filter_ids);
      const resultStrategies = this.normalizeIdList(result.selected_strategy_ids);
      const filterSelectionMatches = this.sameIdSet(selectionSnapshot.filter, resultFilters);
      const strategySelectionMatches = this.sameIdSet(selectionSnapshot.strategy, resultStrategies);
      this.setRulesSelectionProof("backend_response", selectionSnapshot.filter, selectionSnapshot.strategy, {
        backend_filter_ids: resultFilters.slice(),
        backend_strategy_ids: resultStrategies.slice(),
        response_filter_matches_payload: filterSelectionMatches,
        response_strategy_matches_payload: strategySelectionMatches
      });

      if (!filterSelectionMatches || !strategySelectionMatches) {
        this.state.dashboardRuleSelectionDraft = {
          filter: selectionSnapshot.filter.slice(),
          strategy: selectionSnapshot.strategy.slice()
        };
        this.state.dashboardRuleSelectionSaving = false;
        this.pushRuleLog("HATA: Backend seçim doğrulaması başarısız. Gönderilen seçim korunuyor.");
        this.render();
        return;
      }

      if (this.auditAction) {
        try {
          await this.auditAction("rule_selection_save", "ok", "Dashboard active rule seçimi kaydedildi.", {
            selected_filters: selectionSnapshot.filter,
            selected_strategies: selectionSnapshot.strategy
          });
        } catch (auditError) {
          this.pushRuleLog("UYARI: Selection save audit yazılamadı; kayıt başarılı kabul edildi.");
        }
      }

      HMTSTC_DATA.rules = Object.assign({}, HMTSTC_DATA.rules || {}, {
        selected_filter_ids: resultFilters,
        selected_strategy_ids: resultStrategies
      });
      this.state.lastKnownRulesSelection = {
        filter: resultFilters.slice(),
        strategy: resultStrategies.slice()
      };
      this.state.dashboardRuleSelectionDraft = null;
      this.state.dashboardRuleSelectionSaving = false;

      try {
        if (this.syncApiData) {
          await this.syncApiData({ skipHeavySync: true });
        } else {
          await this.refreshRulesData();
        }
      } catch (syncError) {
        this.pushRuleLog("UYARI: Seçim kaydedildi ancak sync yenilemesi tamamlanamadı.");
      }
      const refreshSelection = this.dashboardActiveSelectionSnapshot();
      const refreshMatches = this.sameIdSet(selectionSnapshot.filter, refreshSelection.filter) &&
        this.sameIdSet(selectionSnapshot.strategy, refreshSelection.strategy);
      this.setRulesSelectionProof("core_refresh", selectionSnapshot.filter, selectionSnapshot.strategy, {
        backend_filter_ids: resultFilters.slice(),
        backend_strategy_ids: resultStrategies.slice(),
        refreshFilterIds: refreshSelection.filter.slice(),
        refreshStrategyIds: refreshSelection.strategy.slice(),
        mismatch: !refreshMatches,
        mismatchStage: refreshMatches ? "" : "core_refresh"
      });
      this.pushRuleLog(
        refreshMatches
          ? ("SEÇİM: " + resultFilters.length + " filtre / " + resultStrategies.length + " strateji kaydedildi.")
          : "HATA: Seçim kaydı backend refresh sonrası değişti. Lütfen tekrar dene."
      );
      this.render();
    } catch (error) {
      this.state.dashboardRuleSelectionDraft = {
        filter: selectionSnapshot.filter.slice(),
        strategy: selectionSnapshot.strategy.slice()
      };
      this.state.dashboardRuleSelectionSaving = false;
      this.pushRuleLog("HATA: Dashboard seçimi kaydedilemedi. Seçim ekranda korunuyor.");
      if (error && error.apiErrorType === "request_aborted") {
        this.pushRuleLog("HATA: İstek iptal edildi; tekrar dene.");
      } else {
        this.pushRuleLog("HATA: " + this.apiErrorMessage(error, "Backend hatası."));
      }

      if (this.auditAction) {
        try {
          await this.auditAction("rule_selection_save", "error", "Dashboard active rule seçimi kaydedilemedi.", {});
        } catch (auditError) {
          this.pushRuleLog("UYARI: Selection save hata audit kaydı yazılamadı.");
        }
      }

      this.render();
    } finally {
      if (this.state.dashboardRuleSelectionSaving) {
        this.state.dashboardRuleSelectionSaving = false;
      }
    }
  },

  activatePaperLabRules: async function () {
    if (this.state.paperLabRunning) {
      this.pushRuleLog("UYARI: Paper Lab çalışması zaten devam ediyor.");
      return;
    }

    const activeSelectionBefore = this.dashboardActiveSelectionSnapshot();
    const paperLabStartedAt = new Date().toLocaleTimeString("tr-TR");

    this.state.paperLabEngineStatus = "running";
    this.state.paperLabRunning = true;
    this.state.paperLabStartedAt = paperLabStartedAt;
    this.state.paperLabCompletedAt = null;
    HMTSTC_DATA.paperLabStatus = {
      status: "running",
      source: "activate_paper_lab",
      message: "Paper Lab tüm uygun filtre/strateji kombinasyonlarıyla çalışıyor.",
      started_at: paperLabStartedAt,
      updated_at: paperLabStartedAt
    };
    this.pushRuleLog("PAPER LAB: Dashboard seçiminden bağımsız laboratuvar çalışması başlatıldı.");

    try {
      const result = await this.fetchJson("/api/rules/activate-paper-lab", {
        method: "POST",
        requestKind: "mutation",
        preventGlobalAbort: true,
        timeoutMs: 15000,
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          paper_lab_scope: "all_eligible"
        })
      });

      this.pushRuleLog(
        "PAPER LAB: " +
        result.accepted_combinations +
        " kombinasyon kabul, " +
        result.rejected_combinations +
        " reddedildi."
      );

      const activationLogs = result.activation && Array.isArray(result.activation.logs)
        ? result.activation.logs
        : [];

      activationLogs.forEach(function (item) {
        if (item.accepted) return;

        const reasons = Array.isArray(item.reasons) && item.reasons.length
          ? item.reasons.join(", ")
          : "sebep belirtilmedi";

        HMTSTC_APP.pushRuleLog(
          "RED: " +
          item.filter_id +
          " + " +
          item.strategy_id +
          " → " +
          reasons
        );
      });

      if (this.auditAction) {
        try {
          await this.auditAction("paper_lab_activate", "ok", "Paper Lab bağımsız kombinasyon çalışması tamamlandı.", {
            model_count: result.model_count,
            run_id: result.run_id || ((result.activation || {}).id)
          });
        } catch (auditError) {
          this.pushRuleLog("UYARI: Paper Lab audit yazılamadı; çalışma başarılı kabul edildi.");
        }
      }

      const paperLabCompletedAt = result.completed_at || new Date().toLocaleTimeString("tr-TR");
      const paperLabRunId = result.run_id || ((result.activation || {}).id) || "";
      const paperLabCandidateCount = Number(result.paper_lab_candidate_count || 0);
      const paperLabModelCount = Number(result.model_count || 0);
      const paperLabAccepted = Number(result.accepted_combinations || 0);
      const paperLabRejected = Number(result.rejected_combinations || 0);

      this.state.paperLabEngineStatus = "completed";
      this.state.paperLabRunId = paperLabRunId;
      this.state.paperLabCandidateCount = paperLabCandidateCount;
      this.state.paperLabModelCount = paperLabModelCount;
      this.state.paperLabAccepted = paperLabAccepted;
      this.state.paperLabRejected = paperLabRejected;
      this.state.paperLabCompletedAt = paperLabCompletedAt;
      this.state.paperLabRun = {
        run_id: paperLabRunId,
        paper_lab_filter_count: (result.paper_lab_filter_ids || []).length,
        paper_lab_strategy_count: (result.paper_lab_strategy_ids || []).length,
        paper_lab_candidate_count: paperLabCandidateCount,
        started_at: paperLabStartedAt,
        completed_at: paperLabCompletedAt
      };
      this.state.lastPaperLabResult = {
        status: "completed",
        source: "activate_paper_lab",
        started_at: paperLabStartedAt,
        completed_at: paperLabCompletedAt,
        updated_at: paperLabCompletedAt,
        selected_filter_count: (result.paper_lab_filter_ids || []).length,
        selected_strategy_count: (result.paper_lab_strategy_ids || []).length,
        paper_lab_candidate_count: paperLabCandidateCount,
        accepted_combinations: paperLabAccepted,
        rejected_combinations: paperLabRejected,
        model_count: paperLabModelCount,
        run_id: paperLabRunId,
        message: "Paper Lab bağımsız çalışması tamamlandı."
      };
      HMTSTC_DATA.paperLabStatus = Object.assign({}, HMTSTC_DATA.paperLabStatus || {}, this.state.lastPaperLabResult);
      if (this.applyPaperLabStatusPayload) {
        this.applyPaperLabStatusPayload(result.paper_lab_status || result, "activate_paper_lab_persistent_store");
      }
      if (this.fetchPaperLabStatus) {
        await this.fetchPaperLabStatus({ force: true, render: false, source: "paper_lab_force_refresh" });
      }

      try {
        if (this.syncApiData) {
          await this.syncApiData({ skipHeavySync: true, skipPaperLabStatusFetch: true });
        } else {
          await this.refreshRulesData();
        }
      } catch (syncError) {
        this.pushRuleLog("UYARI: Paper Lab başarılı kaydedildi; ancak son refresh tamamlanamadı.");
      }

      const activeSelectionAfter = this.dashboardActiveSelectionSnapshot();
      const paperLabSelectionMatches = this.sameIdSet(activeSelectionBefore.filter, activeSelectionAfter.filter) &&
        this.sameIdSet(activeSelectionBefore.strategy, activeSelectionAfter.strategy);
      this.setRulesSelectionProof("paper_lab_after_refresh", activeSelectionBefore.filter, activeSelectionBefore.strategy, {
        afterPaperLabFilterIds: activeSelectionAfter.filter.slice(),
        afterPaperLabStrategyIds: activeSelectionAfter.strategy.slice(),
        mismatch: !paperLabSelectionMatches,
        mismatchStage: paperLabSelectionMatches ? "" : "paper_lab_after_refresh"
      });

      this.render();
    } catch (error) {
      const message = this.apiErrorMessage(error, "Backend hatası.");
      const failedAt = new Date().toLocaleTimeString("tr-TR");
      this.state.paperLabEngineStatus = "failed";
      this.state.paperLabCompletedAt = failedAt;
      HMTSTC_DATA.paperLabStatus = {
        status: "failed",
        source: "activate_paper_lab",
        message: message,
        started_at: paperLabStartedAt,
        completed_at: failedAt,
        updated_at: failedAt
      };

      if (error && error.apiErrorType === "request_aborted") {
        this.pushRuleLog("HATA: İstek iptal edildi; tekrar dene.");
      } else {
        this.pushRuleLog("HATA: Paper Lab çalışması başarısız - " + message);
      }

      if (this.auditAction) {
        try {
          await this.auditAction("paper_lab_activate", "error", "Paper Lab çalışması başarısız.", {});
        } catch (auditError) {
          this.pushRuleLog("UYARI: Paper Lab hata audit kaydı yazılamadı.");
        }
      }

      this.render();
    } finally {
      this.state.paperLabRunning = false;
    }
  },

  exportRulesDebugFile: async function () {
    let payload = HMTSTC_DATA.rules || {};

    try {
      const result = await this.fetchJson("/api/rules", {
        requestKind: "core_read",
        timeoutMs: 10000
      });
      payload = result || payload;
    } catch (error) {
      this.pushRuleLog("UYARI: Backend'den güncel rule alınamadı, ekrandaki local veri export ediliyor.");
    }

    const rules = Array.isArray(payload.rules) ? payload.rules : [];
    const filters = Array.isArray(payload.filters)
      ? payload.filters
      : rules.filter(function (item) { return item && item.type === "filter"; });

    const strategies = Array.isArray(payload.strategies)
      ? payload.strategies
      : rules.filter(function (item) { return item && item.type === "strategy"; });

    const exportPayload = {
      exported_at: new Date().toISOString(),
      total_rules: rules.length,
      filters_count: filters.length,
      strategies_count: strategies.length,
      filters: filters,
      strategies: strategies,
      raw_payload: payload
    };

    const blob = new Blob([JSON.stringify(exportPayload, null, 2)], {
      type: "application/json"
    });

    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = "hmtstc-rules-debug-export.json";
    a.click();
    URL.revokeObjectURL(url);

    this.pushRuleLog("EXPORT: Filtre ve stratejiler tek JSON dosyası olarak indirildi.");
  },

  bulkFixRuleMetrics: async function () {
    const metricMap = {
      "quote_volume_24h": "quote_volume",
      "volume_sma20": "volume_sma",
      "ema20": "ema_20",
      "ema50": "ema_50",
      "ema100": "ema_100"
    };

    const removeMetrics = [
      "bid_price",
      "ask_price",
      "order_book_depth"
    ];

    function fixMetricName(value) {
      const clean = String(value || "");
      return metricMap[clean] || clean;
    }

    function fixRuleBlock(block) {
      if (!block || typeof block !== "object") return block;

      if (block.metric) {
        block.metric = fixMetricName(block.metric);
      }

      if (block.value_metric) {
        block.value_metric = fixMetricName(block.value_metric);
      }

      return block;
    }

    function fixRule(rule) {
      const copy = JSON.parse(JSON.stringify(rule));

      if (Array.isArray(copy.required_metrics)) {
        copy.required_metrics = copy.required_metrics
          .map(fixMetricName)
          .filter(function (metric) {
            return removeMetrics.indexOf(metric) === -1;
          });
      }

      ["conditions", "avoid_conditions", "score_rules", "entry_rules", "exit_rules", "long_conditions", "short_conditions"].forEach(function (key) {
        if (Array.isArray(copy[key])) {
          copy[key] = copy[key].map(fixRuleBlock);
        }
      });

      copy.version = Number(copy.version || 1) + 1;
      copy.updated_at = new Date().toISOString();

      return copy;
    }

    try {
      const payload = await this.fetchJson("/api/rules", {
        requestKind: "core_read",
        timeoutMs: 10000
      });
      const rules = Array.isArray(payload.rules) ? payload.rules : [];

      if (!rules.length) {
        this.pushRuleLog("UYARI: Düzeltilecek filtre/strateji bulunamadı.");
        return;
      }

      let fixedCount = 0;

      for (const rule of rules) {
        const fixed = fixRule(rule);

        await this.fetchJson("/api/rules/save", {
          method: "POST",
          requestKind: "mutation",
          preventGlobalAbort: true,
          timeoutMs: 15000,
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ rule: fixed })
        });

        fixedCount += 1;
      }

      this.pushRuleLog("TOPLU DÜZELTME: " + fixedCount + " filtre/strateji normalize edildi.");
      await this.refreshRulesData();
    } catch (error) {
      this.pushRuleLog("HATA: Toplu metric düzeltme başarısız - " + this.apiErrorMessage(error, "Backend hatası."));
      this.render();
    }
  },

  autoBuildPaperLabModels: async function () {
    const system = HMTSTC_DATA.systemStatus || {};
    const authExpired =
      system.auth_status === "auth_expired" ||
      system.last_api_error_type === "http_401" ||
      HMTSTC_APP.state.auth === false;

    if (authExpired) {
      HMTSTC_DATA.paperLabStatus = {
        status: "auth_expired",
        message: "Oturum süresi doldu. Tekrar giriş yap.",
        updated_at: new Date().toLocaleTimeString("tr-TR")
      };
      this.pushRuleLog("HATA: Oturum süresi doldu. Auto Paper Lab başlatılmadı; filtre/strateji listesi korunuyor.");
      this.render();
      return;
    }

    try {
      const freshRules = await this.fetchJson("/api/rules", {
        requestKind: "core_read",
        timeoutMs: 10000
      });
      if (freshRules && typeof freshRules === "object") {
        if (this.preserveOrApplyRulesPayload) {
          const rulesApplied = this.preserveOrApplyRulesPayload(freshRules, "auto_paper_lab_precheck");
          if (!rulesApplied) {
            this.pushRuleLog("HATA: Backend rule listesi güvenli doğrulanamadı; Auto Paper Lab başlatılmadı.");
            this.render();
            return;
          }
        } else {
          HMTSTC_DATA.rules = freshRules;
        }
      } else {
        this.pushRuleLog("HATA: Backend rule listesi geçersiz; Auto Paper Lab başlatılmadı.");
        this.render();
        return;
      }
    } catch (error) {
      const type = error && error.apiErrorType;
      if (type === "http_401" || (error && error.status === 401)) {
        this.pushRuleLog("HATA: Oturum süresi doldu. Filtre/strateji listesi korunuyor; tekrar giriş yap.");
      } else if (type === "http_403" || (error && error.status === 403)) {
        this.pushRuleLog("HATA: Yetki yetersiz. Paper Lab için rol/izin kontrol edilmeli.");
      } else if (type === "request_aborted") {
        this.pushRuleLog("HATA: İstek iptal edildi; tekrar dene.");
      } else if (type === "backend_offline" || type === "timeout" || type === "unknown_network") {
        this.pushRuleLog("HATA: Backend erişilemiyor. /api/rules okunamadı.");
      } else {
        this.pushRuleLog("HATA: Rule listesi alınamadı - " + this.apiErrorMessage(error, "Backend hatası."));
      }
      this.render();
      return;
    }

    const rules = HMTSTC_DATA.rules || {};
    const filters = Array.isArray(rules.filters) ? rules.filters : [];
    const strategies = Array.isArray(rules.strategies) ? rules.strategies : [];

    if (!filters.length || !strategies.length) {
      HMTSTC_DATA.paperLabStatus = {
        status: "empty_rules",
        filter_count: filters.length,
        strategy_count: strategies.length,
        message: !filters.length && !strategies.length ? "Rule store boş." : (!filters.length ? "Filtre yok." : "Strateji yok."),
        updated_at: new Date().toLocaleTimeString("tr-TR")
      };
      this.pushRuleLog("HATA: Auto Paper Lab için filtre ve strateji gerekli. Filtre=" + filters.length + ", Strateji=" + strategies.length);
      this.render();
      return;
    }

    HMTSTC_DATA.paperLabStatus = {
      status: "syncing",
      filter_count: filters.length,
      strategy_count: strategies.length,
      updated_at: new Date().toLocaleTimeString("tr-TR")
    };
    this.pushRuleLog("AUTO PAPER LAB: Tüm filtre ve stratejiler otomatik eşleştiriliyor...");

    try {
      const result = await this.fetchJson("/api/rules/auto-paper-lab", {
        method: "POST",
        requestKind: "mutation",
        preventGlobalAbort: true,
        timeoutMs: 15000,
        headers: { "Content-Type": "application/json" }
      });

      this.pushRuleLog(
        "AUTO PAPER LAB: " +
        result.model_count +
        " model aktif. Yeni=" +
        result.added_count +
        ", mevcut=" +
        result.kept_count +
        ", silinen=" +
        result.removed_count +
        ". Red=" +
        result.rejected_combinations
      );

      HMTSTC_DATA.paperLabStatus = {
        status: result.model_count > 0 ? "ready" : "no_model",
        source: "auto_paper_lab",
        model_count: result.model_count || 0,
        accepted_combinations: result.accepted_combinations || 0,
        rejected_combinations: result.rejected_combinations || 0,
        selected_filter_count: filters.length,
        selected_strategy_count: strategies.length,
        message: result.model_count > 0 ? "Paper Lab hazır." : "Model üretildi ama kabul edilen kombinasyon yok.",
        updated_at: new Date().toLocaleTimeString("tr-TR")
      };
      this.state.lastPaperLabResult = Object.assign({}, HMTSTC_DATA.paperLabStatus, {
        added_count: result.added_count || 0,
        kept_count: result.kept_count || 0,
        removed_count: result.removed_count || 0
      });

      const logs = result.activation && Array.isArray(result.activation.logs)
        ? result.activation.logs
        : [];

      logs.slice(-20).forEach(function (item) {
        if (item.accepted) return;

        const reasons = Array.isArray(item.reasons) && item.reasons.length
          ? item.reasons.join(", ")
          : "sebep yok";

        HMTSTC_APP.pushRuleLog(
          "AUTO RED: " +
          item.filter_id +
          " + " +
          item.strategy_id +
          " → " +
          reasons
        );
      });

      if (this.auditAction) {
        try {
          await this.auditAction("auto_paper_lab_sync", "ok", "Otomatik Paper Lab senkronizasyonu tamamlandı.", {
            model_count: result.model_count,
            added_count: result.added_count,
            kept_count: result.kept_count,
            removed_count: result.removed_count
          });
        } catch (auditError) {
          this.pushRuleLog("UYARI: Auto Paper Lab audit yazılamadı; senkronizasyon başarılı kabul edildi.");
        }
      }

      try {
        if (this.syncApiData) {
          await this.syncApiData({ skipHeavySync: true, skipPaperLabStatusFetch: true });
        } else {
          await this.refreshRulesData();
        }
      } catch (syncError) {
        this.pushRuleLog("UYARI: Paper Lab başarılı kaydedildi; ancak son refresh tamamlanamadı.");
      }
    } catch (error) {
      const type = error && error.apiErrorType;
      const message = this.apiErrorMessage(error, "Backend hatası.");
      HMTSTC_DATA.paperLabStatus = {
        status: "error",
        error_type: type || "unknown",
        message: message,
        updated_at: new Date().toLocaleTimeString("tr-TR")
      };
      if (type === "request_aborted") {
        this.pushRuleLog("HATA: İstek iptal edildi; tekrar dene.");
      } else if (type === "http_404") {
        this.pushRuleLog("HATA: Endpoint bulunamadı: /api/rules/auto-paper-lab");
      } else if (type === "http_401" || (error && error.status === 401)) {
        this.pushRuleLog("HATA: Oturum süresi doldu. Filtre/strateji listesi korunuyor; tekrar giriş yap.");
      } else if (type === "http_403" || (error && error.status === 403)) {
        this.pushRuleLog("HATA: Yetki yetersiz. Paper Lab için rol/izin kontrol edilmeli.");
      } else if (type === "backend_offline" || type === "timeout" || type === "unknown_network") {
        this.pushRuleLog("HATA: Backend erişilemiyor. Auto Paper Lab tamamlanamadı.");
      } else {
        this.pushRuleLog("HATA: Otomatik Paper Lab senkronizasyonu başarısız - " + message);
      }
      this.render();
    }
  },


  pushRuleLog: function (line) {
    const logs = Array.isArray(HMTSTC_DATA.ruleLocalLogs) ? HMTSTC_DATA.ruleLocalLogs : [];

    logs.push({
      time: new Date().toLocaleTimeString("tr-TR"),
      message: line
    });

    HMTSTC_DATA.ruleLocalLogs = logs.slice(-50);
    HMTSTC_DATA.ruleNotice = {
      time: new Date().toLocaleTimeString("tr-TR"),
      message: line
    };

    this.render();
  }


};
