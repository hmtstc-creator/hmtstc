window.HMTSTC_APP_REAL_APPROVAL = {
  decideRealModelApproval: async function (decision, candidateId) {
    if (!candidateId) {
      const approval = HMTSTC_DATA.realApproval || {};
      candidateId = ((approval.recommendation || {}).candidate_model_id || "");
    }
    if (!candidateId) {
      alert("Aday model bulunamadı.");
      return;
    }
    const label = decision === "approve" ? "onaylansın" : "reddedilsin";
    if (!confirm(candidateId + " real model adayı " + label + " mı? Gerçek emir açılmaz.")) return;
    try {
      const result = await this.fetchJson("/api/models/real-approval/decision", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ decision: decision, candidate_model_id: candidateId })
      });
      await this.auditAction("real_model_approval", "ok", result.decision + ": " + candidateId, { candidate_model_id: candidateId });
      await this.syncApiData();
    } catch (error) {
      const msg = this.apiErrorMessage(error, "Real model approval işlemi başarısız.");
      await this.auditAction("real_model_approval", "error", msg, { candidate_model_id: candidateId, decision: decision });
      alert(msg);
    }
  },

  applyRiskProfile: async function (profileId) {
    if (!profileId) return;
    if (!confirm(profileId + " risk profili uygulansın mı?")) return;
    try {
      await this.fetchJson("/api/settings/risk-profiles/" + encodeURIComponent(profileId), { method: "POST" });
      await this.auditAction("settings_risk_profile", "ok", profileId, { profile_id: profileId });
      await this.syncApiData();
    } catch (error) {
      const msg = this.apiErrorMessage(error, "Risk profili uygulanamadı.");
      await this.auditAction("settings_risk_profile", "error", msg, { profile_id: profileId });
      alert(msg);
    }
  },

  exportReports: async function () {
    try {
      const result = await this.fetchJson("/api/models/reports/export?period=7d&format=json");
      const blob = new Blob([JSON.stringify(result, null, 2)], { type: "application/json" });
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = "hmtstc-report-7d.json";
      a.click();
      URL.revokeObjectURL(url);
      await this.auditAction("reports_export", "ok", "7d report exported", {});
    } catch (error) {
      alert(this.apiErrorMessage(error, "Rapor export alınamadı."));
    }
  }
};

Object.assign(window.HMTSTC_APP_REAL_APPROVAL, {
  confirmAction: function (options) {
    options = options || {};
    return new Promise(function (resolve) {
      HMTSTC_APP.state.confirmModal = {
        title: options.title || "İşlem Onayı",
        message: options.message || "Bu işlem uygulansın mı?",
        level: options.level || "warn",
        confirmText: options.confirmText || "Onayla",
        cancelText: options.cancelText || "Vazgeç",
        onConfirm: function () { HMTSTC_APP.state.confirmModal = null; HMTSTC_APP.render(); resolve(true); },
        onCancel: function () { HMTSTC_APP.state.confirmModal = null; HMTSTC_APP.render(); resolve(false); }
      };
      HMTSTC_APP.render();
    });
  },

  exportReportsCsv: async function () {
    try {
      const result = await this.fetchJson("/api/models/reports/export?period=7d&format=csv");
      const blob = new Blob([result.csv || ""], { type: "text/csv" });
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = "hmtstc-report-7d.csv";
      a.click();
      URL.revokeObjectURL(url);
      await this.auditAction("reports_export_csv", "ok", "7d report exported as CSV", {});
    } catch (error) {
      alert(this.apiErrorMessage(error, "CSV rapor export alınamadı."));
    }
  },

  archiveReportSnapshot: async function () {
    const ok = await this.confirmAction({ title: "Rapor Snapshot", message: "7 günlük rapor arşive alınsın mı?", level: "info", confirmText: "Arşivle" });
    if (!ok) return;
    try {
      await this.fetchJson("/api/models/reports/archive?period=7d", { method: "POST" });
      await this.auditAction("reports_archive", "ok", "7d report archived", {});
      await this.syncApiData();
    } catch (error) {
      alert(this.apiErrorMessage(error, "Rapor arşivlenemedi."));
    }
  },

  dryRunRealOrder: async function (symbol) {
    const ok = await this.confirmAction({ title: "Dry-run Real Order", message: "Gerçek emir gönderilmez. Safety layer sadece simülasyon yapar.", level: "critical", confirmText: "Dry-run Çalıştır" });
    if (!ok) return;
    try {
      const result = await this.fetchJson("/api/models/real-order/dry-run", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ symbol: symbol || "BTCUSDT", side: "BUY", usdt_size: 50 })
      });
      alert(result.status + " | " + (result.blockers || []).join(", "));
      await this.auditAction("real_order_dry_run", result.status, result.message || "dry-run", result);
    } catch (error) {
      alert(this.apiErrorMessage(error, "Real order dry-run başarısız."));
    }
  }
});
