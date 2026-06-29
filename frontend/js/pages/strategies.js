window.HMTSTC_PAGES = window.HMTSTC_PAGES || {};

window.HMTSTC_PAGES.strategies = function () {
  const reports = HMTSTC_DATA.reports || {};

  function esc(value) {
    return HMTSTC_APP.escapeHtml(value === undefined || value === null ? "" : value);
  }

  function arr(value) {
    return Array.isArray(value) ? value : [];
  }

  function num(value, fallback) {
    const parsed = Number(value);
    return Number.isFinite(parsed) ? parsed : (fallback || 0);
  }

  function fmt(value, digits) {
    return num(value, 0).toLocaleString("tr-TR", {
      minimumFractionDigits: digits === undefined ? 2 : digits,
      maximumFractionDigits: digits === undefined ? 2 : digits
    });
  }

  function money(value) {
    return fmt(value, 2) + " USDT";
  }

  function pct(value) {
    return fmt(value, 2) + "%";
  }

  function statusClass(status) {
    const raw = String(status || "").toLowerCase();
    if (["ok", "ready", "strong", "healthy", "locked"].indexOf(raw) !== -1) return "ok";
    if (["blocked", "error", "bad", "danger", "failed"].indexOf(raw) !== -1) return "blocked";
    return "review";
  }

  function modelBand(score, trades) {
    const s = num(score, 0);
    const t = num(trades, 0);
    if (!t) return { label: "Veri yok", cls: "review" };
    if (s >= 75) return { label: "Güçlü", cls: "ok" };
    if (s >= 55) return { label: "İzle", cls: "review" };
    return { label: "Zayıf", cls: "blocked" };
  }

  function emptyRow(colspan, message) {
    return '<tr><td colspan="' + colspan + '" class="paper-empty-cell">' + esc(message) + '</td></tr>';
  }

  function modelRows() {
    const rows = arr(reports.model_ranking).slice(0, 10);
    if (!rows.length) return emptyRow(7, "Paper Lab model sonucu bekleniyor.");

    return rows.map(function (row) {
      const band = modelBand(row.score, row.total_trades);
      return '<tr>' +
        '<td><b>' + esc(row.model_id || "-") + '</b><small>' + esc(row.filter_id || "-") + ' / ' + esc(row.strategy_id || "-") + '</small></td>' +
        '<td>' + fmt(row.score, 2) + '</td>' +
        '<td class="' + (num(row.total_pnl) >= 0 ? 'pos' : 'neg') + '">' + money(row.total_pnl) + '</td>' +
        '<td>' + pct(row.win_rate) + '</td>' +
        '<td>' + esc(row.total_trades || 0) + '</td>' +
        '<td>' + pct(row.max_drawdown_percent) + '</td>' +
        '<td><span class="status-pill ' + band.cls + '">' + esc(band.label) + '</span></td>' +
      '</tr>';
    }).join("");
  }

  function rankRows(items, kind) {
    const rows = arr(items).slice(0, 8);
    if (!rows.length) return emptyRow(5, kind + " sonucu bekleniyor.");

    return rows.map(function (row) {
      const id = row.filter_id || row.strategy_id || row.id || "-";
      return '<tr>' +
        '<td><b>' + esc(id) + '</b></td>' +
        '<td>' + esc(row.models_count || 0) + '</td>' +
        '<td>' + fmt(row.avg_score, 2) + '</td>' +
        '<td>' + pct(row.weighted_win_rate) + '</td>' +
        '<td class="' + (num(row.total_pnl) >= 0 ? 'pos' : 'neg') + '">' + money(row.total_pnl) + '</td>' +
      '</tr>';
    }).join("");
  }

  function metricCard(label, value, hint, cls) {
    return '<div class="paper-kpi-card ' + (cls || '') + '">' +
      '<span>' + esc(label) + '</span>' +
      '<b>' + esc(value) + '</b>' +
      '<small>' + esc(hint || '') + '</small>' +
    '</div>';
  }

  function infoRow(label, value) {
    return '<div class="paper-info-row"><span>' + esc(label) + '</span><b>' + esc(value) + '</b></div>';
  }

  function reportCard(title, subtitle, status, body) {
    return '<section class="paper-report-card status-' + statusClass(status) + '">' +
      '<div class="paper-report-card-title"><div><b>' + esc(title) + '</b><span>' + esc(subtitle || '') + '</span></div>' +
      '<em class="status-pill ' + statusClass(status) + '">' + esc(status || 'review') + '</em></div>' +
      body +
    '</section>';
  }

  const paper = reports.paper_lab || {};
  const livePaper = HMTSTC_DATA.paperLabStatus || {};
  const persistentLastRun = livePaper.last_run && typeof livePaper.last_run === "object" ? livePaper.last_run : {};
  const lastPaper = (HMTSTC_APP.state && HMTSTC_APP.state.lastPaperLabResult) || {};
  const paperSummary = Object.assign({}, livePaper, persistentLastRun, lastPaper);
  const fingerprintMatches = livePaper.last_run_matches_current_rules === true;
  const hasPersistentRun = Boolean(persistentLastRun.run_id || paperSummary.run_id);
  const paperLabStatusLoading = Boolean(HMTSTC_APP.state && HMTSTC_APP.state.paperLabStatusLoading && !hasPersistentRun);
  const isolatedPaperLabLoadingMessage = paperLabStatusLoading ? "Paper Lab sonucu yükleniyor..." : "";
  const score = reports.score_breakdown || {};
  const execution = reports.execution_quality_summary || {};
  const drift = reports.simulator_drift || {};
  const driftInfo = drift.drift || {};
  const wallet = reports.paper_wallet_integrity || {};
  const position = reports.paper_position_integrity || {};

  const strong = num(score.strong_models, 0);
  const watch = num(score.watch_models, 0);
  const weak = num(score.weak_models, 0);
  const topModel = arr(reports.model_ranking)[0] || {};

  const topKpis = [
    metricCard("Model", paperSummary.model_count || paper.models_count || arr(reports.model_ranking).length || 0, "Paper Lab kombinasyon sayısı"),
    metricCard("En iyi skor", topModel.score !== undefined ? fmt(topModel.score, 2) : "-", topModel.model_id || "Model bekleniyor", num(topModel.score) >= 75 ? "good" : ""),
    metricCard("Güçlü / İzle / Zayıf", strong + " / " + watch + " / " + weak, "Score breakdown özeti"),
    metricCard("Execution", fmt(execution.avg_execution_quality, 2), "Ortalama işlem kalitesi", statusClass(execution.status)),
    metricCard("Simülasyon", fmt(drift.calibration_score, 2), "Paper / dry-run güven skoru", statusClass(drift.status)),
    metricCard("Veri bütünlüğü", (wallet.status || "-") + " / " + (position.status || "-"), "Cüzdan ve pozisyon kontrolü", statusClass(wallet.status === "ok" && position.status === "ok" ? "ok" : "review"))
  ].join("");

  const lastRunPanel = '<section class="paper-report-panel paper-last-run-panel">' +
    '<div class="paper-panel-title"><div><b>Son Paper Lab Çalışması</b><span>Backend kalıcı Paper Lab store kaydı</span></div><em>' + esc(paperLabStatusLoading ? "yükleniyor" : (paperSummary.status || "beklemede")) + '</em></div>' +
    '<div class="paper-integrity-grid">' +
      reportCard("Durum", "Kalıcı son run", paperSummary.status || "review", [
        infoRow("Son run zamanı", paperSummary.completed_at || paperSummary.updated_at || "-"),
        infoRow("Run id", paperSummary.run_id || "-"),
        infoRow("Kaynak", paperSummary.source || (livePaper.store_persistent ? "paper_lab_store.json" : "-")),
        infoRow("Mesaj", isolatedPaperLabLoadingMessage || paperSummary.message || (hasPersistentRun ? "Paper Lab sonucu backend store'dan yüklendi." : "Paper Lab sonucu bekleniyor."))
      ].join("")) +
      reportCard("Kombinasyon", "Filtre x strateji sonucu", paperSummary.status || "review", [
        infoRow("Filtre", paperSummary.selected_filter_count || paperSummary.filter_count || 0),
        infoRow("Strateji", paperSummary.selected_strategy_count || paperSummary.strategy_count || 0),
        infoRow("Candidate", paperSummary.paper_lab_candidate_count || paperSummary.candidate_count || 0),
        infoRow("Kabul / Red", (paperSummary.accepted_combinations || 0) + " / " + (paperSummary.rejected_combinations || 0)),
        infoRow("Model", paperSummary.model_count || 0)
      ].join("")) +
      reportCard("Fingerprint", "Mevcut rule seti eşleşmesi", fingerprintMatches ? "ok" : (hasPersistentRun ? "review" : "beklemede"), [
        infoRow("Rules fingerprint match", hasPersistentRun ? (fingerprintMatches ? "Evet" : "Hayır") : "-"),
        infoRow("Run fingerprint", paperSummary.rules_fingerprint || "-"),
        infoRow("Mevcut fingerprint", livePaper.rules_fingerprint || "-"),
        infoRow("Uyarı", hasPersistentRun && !fingerprintMatches ? "Bu Paper Lab sonucu mevcut filtre/strateji setinden önce oluşturuldu." : "Yok")
      ].join("")) +
    '</div>' +
  '</section>';

  const modelTable = '<section class="paper-report-panel paper-model-ranking">' +
    '<div class="paper-panel-title"><div><b>Model Ranking</b><span>En iyi 10 Paper Lab kombinasyonu</span></div><em>max 10</em></div>' +
    '<div class="paper-table-wrap"><table><thead><tr><th>Model</th><th>Skor</th><th>Net PnL</th><th>Win</th><th>İşlem</th><th>DD</th><th>Durum</th></tr></thead><tbody>' + modelRows() + '</tbody></table></div>' +
  '</section>';

  const qualityCards = '<div class="paper-quality-stack">' +
    reportCard("Score Breakdown", "Model skoru neden iyi/kötü?", score.status, [
      infoRow("Ortalama skor", fmt(score.avg_score, 2)),
      infoRow("Execution ort.", fmt(score.avg_execution_quality, 2)),
      infoRow("Stability ort.", fmt(score.avg_stability, 2)),
      infoRow("Mesaj", score.message || "Skor bileşeni bekleniyor.")
    ].join("")) +
    reportCard("Execution Quality", "Paper işlem kalitesi", execution.status, [
      infoRow("Ortalama kalite", fmt(execution.avg_execution_quality, 2)),
      infoRow("Yüksek kalite", arr(execution.high_quality_models).length),
      infoRow("Düşük kalite", execution.low_quality_count || arr(execution.low_quality_models).length || 0),
      infoRow("Mesaj", execution.message || "Execution örneği bekleniyor.")
    ].join("")) +
    reportCard("Simülasyon Güven Skoru", "Paper / dry-run sapma kontrolü", drift.status, [
      infoRow("Kalibrasyon", fmt(drift.calibration_score, 2)),
      infoRow("Paper-Dry delta", driftInfo.paper_vs_dry_run_quality_delta === null || driftInfo.paper_vs_dry_run_quality_delta === undefined ? "Bekleniyor" : fmt(driftInfo.paper_vs_dry_run_quality_delta, 2)),
      infoRow("Paper-Real delta", driftInfo.paper_vs_real_quality_delta === null || driftInfo.paper_vs_real_quality_delta === undefined ? "Bekleniyor" : fmt(driftInfo.paper_vs_real_quality_delta, 2)),
      infoRow("Uyarı", arr(drift.warnings).slice(0, 2).join(" | ") || "Yok")
    ].join("")) +
  '</div>';

  const filterTable = '<section class="paper-report-panel">' +
    '<div class="paper-panel-title"><div><b>Filter Ranking</b><span>En iyi 8 filtre</span></div><em>max 8</em></div>' +
    '<div class="paper-table-wrap compact"><table><thead><tr><th>Filtre</th><th>Model</th><th>Skor</th><th>Win</th><th>PnL</th></tr></thead><tbody>' + rankRows(reports.filter_ranking, "Filtre") + '</tbody></table></div>' +
  '</section>';

  const strategyTable = '<section class="paper-report-panel">' +
    '<div class="paper-panel-title"><div><b>Strategy Ranking</b><span>En iyi 8 strateji</span></div><em>max 8</em></div>' +
    '<div class="paper-table-wrap compact"><table><thead><tr><th>Strateji</th><th>Model</th><th>Skor</th><th>Win</th><th>PnL</th></tr></thead><tbody>' + rankRows(reports.strategy_ranking, "Strateji") + '</tbody></table></div>' +
  '</section>';

  const integrity = '<section class="paper-report-panel paper-integrity-panel">' +
    '<div class="paper-panel-title"><div><b>Integrity</b><span>Cüzdan ve pozisyon veri sağlığı</span></div><em>kontrol</em></div>' +
    '<div class="paper-integrity-grid">' +
      reportCard("Wallet", "Cüzdan tutarlılığı", wallet.status, [
        infoRow("Kontrol edilen model", wallet.checked_models || 0),
        infoRow("Sorun", wallet.issue_count || 0),
        infoRow("Maks. fark", money(wallet.max_delta || 0))
      ].join("")) +
      reportCard("Position", "Pozisyon tutarlılığı", position.status, [
        infoRow("Açık / kapalı", (position.open_positions || 0) + " / " + (position.closed_positions || 0)),
        infoRow("Bozuk kayıt", position.invalid_count || 0),
        infoRow("Duplicate", position.duplicate_count || 0)
      ].join("")) +
    '</div>' +
  '</section>';

  return '<div class="operation-page strategies-page paper-report-page">' +
    '<div class="operation-header"><div><h2>Paper Lab Rapor Merkezi</h2><span>Ham veri yığını değil; model, filtre, strateji, güven ve veri bütünlüğü karar ekranı.</span></div><div class="operation-header-badges"><b>RISK PROFILE YOK</b><b>MAX SATIR LİMİTLİ</b></div></div>' +
    '<div class="paper-report-shell">' +
      '<div class="paper-kpi-grid">' + topKpis + '</div>' +
      lastRunPanel +
      '<div class="paper-report-main-grid">' + modelTable + qualityCards + '</div>' +
      '<div class="paper-report-bottom-grid">' + filterTable + strategyTable + integrity + '</div>' +
    '</div>' +
  '</div>';
};
