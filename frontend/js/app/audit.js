window.HMTSTC_APP_AUDIT = {
  auditAction: async function (action, result, message, meta) {
    meta = meta || {};
    const item = {
      time: new Date().toISOString(),
      user: this.state.user || "default",
      role: this.state.role || "user",
      page: this.state.page || "dashboard",
      endpoint: meta.endpoint || null,
      category: meta.category || "system",
      severity: meta.severity || (result === "error" ? "warning" : "info"),
      action: action || "ui_action",
      result: result || "ok",
      message: message || "",
      meta: meta || {}
    };

    const payload = HMTSTC_DATA.audit || { items: [] };
    payload.items = Array.isArray(payload.items) ? payload.items : [];
    payload.items.push(item);
    payload.items = payload.items.slice(-500);
    HMTSTC_DATA.audit = payload;

    try {
      await this.fetchJson("/api/audit", {
        method: "POST",
        requestKind: "audit_best_effort",
        preventGlobalAbort: true,
        timeoutMs: 8000,
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(item)
      });
    } catch (error) {
      if (error && error.apiErrorType === "request_aborted") {
        HMTSTC_DATA.systemStatus = Object.assign({}, HMTSTC_DATA.systemStatus || {}, {
          audit_status: "warning",
          audit_message: "Audit yazımı iptal edildi; ana işlem korunuyor."
        });
      }
      console.warn("Audit backend yazılamadı:", error.message || error);
    }
  },

  clearAuditTrail: async function () {
    if (!confirm("UI Audit Trail temizlensin mi? Bu işlem owner seviyesinde kritik audit üretir.")) {
      return;
    }

    try {
      await this.fetchJson("/api/audit?confirm=CLEAR_AUDIT", { method: "DELETE" });
      HMTSTC_DATA.audit = { status: "ok", items: [] };
      this.render();
    } catch (error) {
      HMTSTC_DATA.auditMessage = this.apiErrorMessage(error, "Audit temizlenemedi.");
      this.render();
    }
  },

  exportAuditTrail: async function (format) {
    const fmt = (format || "csv").toLowerCase() === "json" ? "json" : "csv";
    try {
      const params = new URLSearchParams({ format: fmt, limit: "2000" });
      if (this.state.auditCategory && this.state.auditCategory !== "all") params.set("category", this.state.auditCategory);
      if (this.state.auditSeverity && this.state.auditSeverity !== "all") params.set("severity", this.state.auditSeverity);
      if (this.state.auditResult && this.state.auditResult !== "all") params.set("result", this.state.auditResult);
      if (this.state.auditUser && this.state.auditUser !== "all") params.set("username", this.state.auditUser);
      if (this.state.auditQuery) params.set("query", this.state.auditQuery);
      const payload = await this.fetchJson("/api/audit/export?" + params.toString());
      const text = fmt === "json" ? JSON.stringify({ manifest: payload.manifest || {}, items: payload.items || [] }, null, 2) : ("# HMTSTC Audit Export Manifest\n# " + JSON.stringify(payload.manifest || {}) + "\n" + (payload.csv || ""));
      const blob = new Blob([text], { type: fmt === "json" ? "application/json;charset=utf-8" : "text/csv;charset=utf-8" });
      const url = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = "hmtstc-audit-export." + fmt;
      link.click();
      URL.revokeObjectURL(url);
      await this.auditAction("audit.export", "ok", "Audit export alındı.", { category: "security", severity: "notice", endpoint: "/api/audit/export", format: fmt });
    } catch (error) {
      HMTSTC_DATA.auditMessage = this.apiErrorMessage(error, "Audit export alınamadı.");
      this.render();
    }
  }
};
