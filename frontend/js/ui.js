window.HMTSTC_UI = {
  card: function (content, className) {
    return '<div class="card ' + (className || '') + '">' + content + '</div>';
  },

  btn: function (text, className, attributes) {
    return '<button class="btn ' + (className || 'btn-main') + '" ' + (attributes || '') + '>' + text + '</button>';
  },

  control: function () {
    const botStatus = HMTSTC_DATA.botStatus || {};
    const dashboard = HMTSTC_DATA.dashboard || {};
    const reports = HMTSTC_DATA.reports || {};
    const state = HMTSTC_APP.state || {};
    const isRunning = botStatus.bot_running === true || dashboard.bot_running === true;
    const apiReady = state.apiReady === true;
    const syncReady = state.apiSyncReady === true;
    const paper = reports.paper_lab || {};
    const recommendation = reports.recommendation || {};
    const role = String((state || {}).role || 'user').toLowerCase();
    const canSeePaperLab = role === 'admin' || role === 'owner';

    function esc(value) {
      return HMTSTC_APP.escapeHtml(value === undefined || value === null ? '' : value);
    }

    function compact(value) {
      return value ? String(value).replace('T', ' ').slice(0, 19) : '-';
    }

    function metric(label, value, note, cls) {
      return '<div class="control-kpi ' + (cls || '') + '"><span>' + esc(label) + '</span><b>' + esc(value) + '</b><em>' + esc(note || '') + '</em></div>';
    }

    function row(label, value) {
      return '<div class="control-row"><span>' + esc(label) + '</span><b>' + esc(value) + '</b></div>';
    }

    const history = HMTSTC_DATA.history || [];
    const totalTrades = history.length;
    const winners = history.filter(function (item) { return Number(item.pnl || 0) > 0; }).length;
    const winRate = totalTrades ? (winners / totalTrades) * 100 : 0;

    return HMTSTC_UI.card(
      '<div class="command-center-grid">' +
        '<div class="command-control-card">' +
          '<div class="control-actions-row">' +
            HMTSTC_UI.btn('Canlı Başlat', 'btn-neutral', 'onclick="HMTSTC_APP.startBot()" ' + ((isRunning || !syncReady) ? 'disabled' : '')) +
            HMTSTC_UI.btn('Canlı Durdur', 'btn-neutral', 'onclick="HMTSTC_APP.stopBot()" ' + ((!isRunning || !syncReady) ? 'disabled' : '')) +
            HMTSTC_UI.btn('Acil Durdur', 'btn-neutral danger-outline', 'onclick="HMTSTC_APP.set({modal:true})" ' + ((!isRunning || !syncReady) ? 'disabled' : '')) +
            (canSeePaperLab ? HMTSTC_UI.btn('Sıfırla', 'btn-neutral reset-outline', 'onclick="HMTSTC_APP.resetBotData()" ' + (!syncReady ? 'disabled' : '')) : '') +
            '<span class="sync-ready-badge ' + (syncReady ? 'sync-ok' : 'sync-wait') + '">' + (syncReady ? 'HAZIR' : 'BEKLE') + '</span>' +
          '</div>' +
          '<div class="cosmic-orbital-visual" aria-label="HMTSTC reactive intelligence visual">' +
            '<div class="cosmic-depth"><span></span><span></span><span></span></div>' +
            '<div class="cosmic-stars"><i></i><i></i><i></i><i></i><i></i><i></i><i></i><i></i><i></i><i></i><i></i><i></i></div>' +
            '<div class="cosmic-core"><b></b><em></em></div>' +
            '<div class="cosmic-orbit orbit-one"><span></span></div>' +
            '<div class="cosmic-orbit orbit-two"><span></span></div>' +
            '<div class="cosmic-orbit orbit-three"><span></span></div>' +
            '<div class="cosmic-links"><span></span><span></span><span></span><span></span></div>' +
          '</div>' +
        '</div>' +

        '<div class="command-summary-card">' +
          '<div class="command-title"><span>HMTSTC Control Center</span><b>Canlı Operasyon</b></div>' +
          '<div class="control-kpi-grid">' +
            metric('Bot', isRunning ? 'Çalışıyor' : 'Kapalı', botStatus.engine_status || dashboard.engine_status || '-', isRunning ? 'good' : 'bad') +
            metric('API', apiReady ? 'Hazır' : 'Bekliyor', state.lastSyncAt || '-', apiReady ? 'good' : 'warn') +
            (canSeePaperLab ? metric('Paper Lab Model', String(paper.models_count || 0), recommendation.action || 'WATCH') : metric('Karar', recommendation.action || 'WATCH', 'Canlı filtre')) +
            metric('Win Rate', winRate.toFixed(2) + '%', totalTrades + ' işlem') +
          '</div>' +
          '<div class="control-compact-rows">' +
            row('Son tick', compact(botStatus.last_tick || dashboard.last_tick)) +
            row('Son scan', compact(botStatus.last_scan_time || dashboard.scan_time)) +
            row('Runtime', botStatus.runtime_text || dashboard.runtime_text || '-') +
            row('Aktif Real Model', (reports.real_model || {}).active_real_model_id || '-') +
          '</div>' +
        '</div>' +

        '<div class="command-health-card">' +
          '<div class="command-title"><span>Risk / Scan</span><b>Operasyon Durumu</b></div>' +
          '<div class="control-compact-rows">' +
            row('Çalışma', 'Canlı') +
            row('Açık pozisyon', dashboard.open_positions || (dashboard.open_positions_count || 0)) +
            row('Taranan coin', dashboard.scanned || 0) +
            row('Aday coin', dashboard.candidates_count || 0) +
            row('En sık eleme', dashboard.top_rejection_reason || '-') +
            row('Öneri', recommendation.action || 'WATCH') +
          '</div>' +
        '</div>' +
      '</div>',
      'command-center-shell'
    );
  },

  posTable: function (rows, compact) {
    const isCompact = compact === true;
    const safeRows = rows || [];

    return '<div class="table-wrap"><table><thead><tr><th>Coin</th><th>Giriş</th><th>Güncel</th>' +
      (isCompact ? '' : '<th>Hedef</th><th>Stop</th>') +
      '<th>PnL</th><th>USDT</th><th>Durum</th></tr></thead><tbody>' +
      safeRows.map(function (p) {
        const pnl = Number(p.pnl || 0);
        return '<tr><td><b>' + p.symbol + '</b></td><td>' + Number(p.entry || 0).toFixed(6) + '</td><td>' + Number(p.current || 0).toFixed(6) + '</td>' +
          (isCompact ? '' : '<td>' + Number(p.target || 0).toFixed(6) + '</td><td>' + Number(p.stop || 0).toFixed(6) + '</td>') +
          '<td class="' + (pnl >= 0 ? 'positive' : 'negative') + '"><b>' + (pnl >= 0 ? '+' : '') + pnl.toFixed(4) + ' USDT</b></td><td>' + Number(p.usdt_size || 0).toFixed(2) + '</td><td><span class="pill">' + (p.status || p.mode || '-') + '</span></td></tr>';
      }).join('') + '</tbody></table></div>';
  },

  pageRole: function (title, role, subtitle, badges) {
    badges = Array.isArray(badges) ? badges : [];
    function esc(v) { return (window.HMTSTC_APP && HMTSTC_APP.escapeHtml ? HMTSTC_APP.escapeHtml(v) : String(v || '')); }
    return '<div class="ux-role-banner ux-product-shell"><div><span class="ux-role-kicker">' + esc(role || 'HMTSTC UI') + '</span><h2>' + esc(title || '-') + '</h2><p>' + esc(subtitle || '') + '</p></div><div class="ux-role-badges">' + badges.map(function (x) { return '<span>' + esc(x) + '</span>'; }).join('') + '</div></div>';
  },

  evidenceStrip: function (items) {
    items = Array.isArray(items) ? items : [];
    function esc(v) { return (window.HMTSTC_APP && HMTSTC_APP.escapeHtml ? HMTSTC_APP.escapeHtml(v) : String(v || '')); }
    return '<div class="ux-evidence-strip">' + items.map(function (item) { return '<div><span>' + esc(item.label || '-') + '</span><b>' + esc(item.value || '-') + '</b><em>' + esc(item.note || '') + '</em></div>'; }).join('') + '</div>';
  },

  criticalActionSpec: function (type) {
    const specs = {
      real_order_place: { level: 'critical', title: 'Real Order Confirmation', confirmText: 'Riskleri anladım' },
      owner_unlock: { level: 'critical', title: 'Owner Unlock Confirmation', confirmText: 'Kilit açma riskini anladım' },
      pilot_start_stop: { level: 'critical', title: 'Micro Pilot Confirmation', confirmText: 'Pilot limitlerini anladım' },
      emergency_close: { level: 'critical', title: 'Emergency Close Confirmation', confirmText: 'Acil kapanışı onayla' },
      rule_restore: { level: 'warn', title: 'Rule Restore Confirmation', confirmText: 'Yeni versiyon olarak geri al' },
      settings_rollback: { level: 'warn', title: 'Settings Rollback Confirmation', confirmText: 'Rollback uygula' }
    };
    return specs[type] || { level: 'warn', title: 'Critical Action', confirmText: 'Onayla' };
  }
};
