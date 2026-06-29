window.HMTSTC_PAGES = window.HMTSTC_PAGES || {};

window.HMTSTC_PAGES.ruleEditor = function () {
  const data = window.HMTSTC_DATA || {};
  const app = window.HMTSTC_APP || {};
  const rulesPayload = data.rules || {};

  const filters = Array.isArray(rulesPayload.filters) ? rulesPayload.filters : [];
  const strategies = Array.isArray(rulesPayload.strategies) ? rulesPayload.strategies : [];

  const reports = data.reports || {};
  const activationLog = Array.isArray(rulesPayload.activation_log) ? rulesPayload.activation_log : [];

  const selectedFilters = Array.isArray(rulesPayload.selected_filter_ids)
    ? rulesPayload.selected_filter_ids.map(String)
    : [];

  const selectedStrategies = Array.isArray(rulesPayload.selected_strategy_ids)
    ? rulesPayload.selected_strategy_ids.map(String)
    : [];

  const activeType = app.state.ruleEditorTab === "strategy" ? "strategy" : "filter";
  const editorActive = ["new", "edit"].indexOf(app.state.ruleEditorMode) !== -1;
  const draft = editorActive && app.getRuleDraft ? app.getRuleDraft(activeType) : "";

  const logs = Array.isArray(data.ruleLocalLogs) ? data.ruleLocalLogs : [];
  const lastLog = logs.length ? logs[logs.length - 1] : null;
  const notice = data.ruleNotice || lastLog;

  const canEdit = app.hasRoleAccess && app.hasRoleAccess(["owner", "admin"]);

  function esc(value) {
    return (app.escapeHtml || function (v) { return String(v || ""); })(
      value === undefined || value === null ? "" : value
    );
  }

  function js(value) {
    return JSON.stringify(String(value === undefined || value === null ? "" : value));
  }

  function compactTime(value) {
    return value ? String(value).replace("T", " ").slice(0, 19) : "-";
  }

  function list(items, type) {
    if (!items.length) {
      return '<div class="simple-rule-empty">' +
        '<b>Kayıt yok</b>' +
        '<span>Yeni butonu ile ' + (type === "strategy" ? "strateji" : "filtre") + ' ekle.</span>' +
      '</div>';
    }

    return '<div class="simple-rule-list">' + items.map(function (item) {
      const id = String(item.id || "");

      return '<div class="simple-rule-item">' +
        '<div>' +
          '<b>' + esc(item.name || id || "İsimsiz") + '</b>' +
          '<span>' + esc(id || "-") + '</span>' +
        '</div>' +

        '<div class="simple-rule-actions">' +
          '<button class="btn btn-ghost btn-small" onclick=\'HMTSTC_APP.loadRuleToEditor(' + js(id) + ')\' ' + (canEdit ? "" : "disabled") + '>Düzelt</button>' +
          '<button class="btn btn-ghost btn-small danger-outline" onclick=\'HMTSTC_APP.deleteRule(' + js(id) + ')\' ' + (canEdit ? "" : "disabled") + '>Sil</button>' +
        '</div>' +
      '</div>';
    }).join("") + '</div>';
  }

  return '<div class="paper-lab-simple-wrap">' +

    (notice
      ? '<div class="simple-rule-notice">' +
          '<b>İşlem durumu</b>' +
          '<span>' + esc(notice.time || "") + ' - ' + esc(notice.message || "") + '</span>' +
        '</div>'
      : ""
    ) +

    '<div class="paper-lab-simple-toolbar">' +
      '<button class="btn btn-ghost" onclick="HMTSTC_APP.exportRulesDebugFile && HMTSTC_APP.exportRulesDebugFile()" ' + (canEdit ? "" : "disabled") + '>Tüm Filtre/Strateji Export</button>' +
      '<button class="btn btn-ghost" onclick="HMTSTC_APP.bulkFixRuleMetrics && HMTSTC_APP.bulkFixRuleMetrics()" ' + (canEdit ? "" : "disabled") + '>Toplu Metric Düzelt</button>' +
      '<button class="btn btn-main" onclick="HMTSTC_APP.autoBuildPaperLabModels ? HMTSTC_APP.autoBuildPaperLabModels() : alert(\'autoBuildPaperLabModels yüklenmedi\')" ' + (canEdit ? "" : "disabled") + '>Otomatik Paper Lab Oluştur</button>' +
    '</div>' +

    '<div class="paper-lab-simple-page">' +

      '<section class="paper-lab-simple-lists">' +

        '<div class="simple-rule-column">' +
          '<div class="simple-rule-column-title">' +
            '<span>Filtreler</span>' +
            '<b>' + filters.length + '</b>' +
          '</div>' +
          list(filters, "filter") +
        '</div>' +

        '<div class="simple-rule-column">' +
          '<div class="simple-rule-column-title">' +
            '<span>Stratejiler</span>' +
            '<b>' + strategies.length + '</b>' +
          '</div>' +
          list(strategies, "strategy") +
        '</div>' +

      '</section>' +

      '<section class="paper-lab-simple-editor ' + (editorActive ? "active" : "disabled") + '">' +

        '<div class="simple-editor-head">' +
          '<div>' +
            '<span>Editör</span>' +
            '<b>' + (editorActive ? esc(app.state.ruleEditorActiveId || "Yeni kayıt") : "Pasif") + '</b>' +
          '</div>' +
          '<button class="btn btn-main btn-small" onclick="HMTSTC_APP.newSimpleRuleDraft()" ' + (canEdit ? "" : "disabled") + '>Yeni</button>' +
        '</div>' +

        '<textarea class="simple-rule-code-editor" ' + (editorActive ? "" : "disabled") + ' spellcheck="false" placeholder="Yeni butonuna basınca editör aktif olur." oninput="HMTSTC_APP.setRuleDraft(document.getElementById(\'simple-rule-type\').value, this.value)">' + esc(draft) + '</textarea>' +

        '<div class="simple-editor-footer">' +
          '<select id="simple-rule-type" onchange="HMTSTC_APP.switchSimpleRuleType(this.value)">' +
            '<option value="filter" ' + (activeType === "filter" ? "selected" : "") + '>Filtre</option>' +
            '<option value="strategy" ' + (activeType === "strategy" ? "selected" : "") + '>Strateji</option>' +
          '</select>' +

          '<button class="btn btn-main btn-small" ' + (editorActive ? "" : "disabled") + ' ' + (canEdit ? "" : "disabled") + ' onclick="HMTSTC_APP.saveSimpleRuleDraft()">Kaydet</button>' +
        '</div>' +

        (lastLog
          ? '<div class="simple-rule-message">' + esc(lastLog.time || "") + ' - ' + esc(lastLog.message || "") + '</div>'
          : ""
        ) +

      '</section>' +

    '</div>' +

  '</div>';
};