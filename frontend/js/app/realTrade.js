window.HMTSTC_APP_REAL_TRADE = {
  refreshRealTrade: async function () {
    try {
      const results = await Promise.allSettled([
        this.fetchJson('/api/real/readiness'),
        this.fetchJson('/api/real/health'),
        this.fetchJson('/api/real/positions'),
        this.fetchJson('/api/real/orders'),
        this.fetchJson('/api/real/pilot'),
        this.fetchJson('/api/real/wallet-integrity'),
        this.fetchJson('/api/real/money-separation'),
        this.fetchJson('/api/real/balances/reconciliation')
      ]);
      const keys = ['realReadiness', 'realHealth', 'realPositions', 'realOrders', 'realPilot', 'realWalletIntegrity', 'realMoneySeparation', 'realBalanceReconciliation'];
      results.forEach(function (result, index) {
        if (result.status === 'fulfilled') HMTSTC_DATA[keys[index]] = result.value;
      });
      this.render();
    } catch (error) {
      HMTSTC_DATA.realTradeMessage = this.apiErrorMessage(error, 'Real trade verisi yenilenemedi.');
      this.render();
    }
  },

  unlockRealTrading: async function () {
    const ok = await this.confirmAction({
      title: 'Real Trade Owner Unlock',
      message: 'Bu işlem gerçek emir göndermez; sadece süreli owner unlock açar. Env, dry-run, safety ve confirmation token kapıları ayrıca geçilmeden gerçek emir gönderilemez.',
      level: 'critical',
      confirmText: 'Süreli Unlock Aç'
    });
    if (!ok) return;
    try {
      const result = await this.fetchJson('/api/real/unlock', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ minutes: 30 })
      });
      await this.auditAction('real_trading.owner_unlock', 'ok', 'Owner unlock açıldı.', { category: 'security', severity: 'critical', endpoint: '/api/real/unlock', result: result });
      await this.syncApiData();
    } catch (error) {
      const msg = this.apiErrorMessage(error, 'Owner unlock açılamadı.');
      await this.auditAction('real_trading.owner_unlock', 'error', msg, { category: 'security', severity: 'blocked', endpoint: '/api/real/unlock' });
      alert(msg);
    }
  },

  lockRealTrading: async function () {
    const ok = await this.confirmAction({
      title: 'Real Trade Kilitle',
      message: 'Real trading owner unlock, pilot ve açık gerçek emir hazırlıkları güvenli moda alınacak.',
      level: 'critical',
      confirmText: 'Kilitle'
    });
    if (!ok) return;
    try {
      const result = await this.fetchJson('/api/real/lock', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ reason: 'manual_ui_lock' })
      });
      await this.auditAction('real_trading.owner_lock', 'ok', 'Real trade manuel kilitlendi.', { category: 'security', severity: 'critical', endpoint: '/api/real/lock', result: result });
      await this.syncApiData();
    } catch (error) {
      alert(this.apiErrorMessage(error, 'Real trade kilitlenemedi.'));
    }
  },

  previewRealOrder: async function (symbol, side, amount) {
    const payload = {
      symbol: String(symbol || HMTSTC_APP.state.realOrderSymbol || 'BTCUSDT').toUpperCase(),
      side: String(side || HMTSTC_APP.state.realOrderSide || 'BUY').toUpperCase(),
      quote_order_qty: Number(String(amount || HMTSTC_APP.state.realOrderAmount || 5).replace(',', '.'))
    };
    try {
      const result = await this.fetchJson('/api/real/orders/preview', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
      });
      HMTSTC_DATA.realOrderPreview = result;
      await this.auditAction('real_order.preview', result.status || 'ok', 'Real order safety preview üretildi.', { category: 'trading', severity: result.status === 'blocked' ? 'blocked' : 'warning', endpoint: '/api/real/orders/preview', payload: payload, result: result });
      this.render();
    } catch (error) {
      alert(this.apiErrorMessage(error, 'Real order preview alınamadı.'));
    }
  },

  dryRunRealOrderV2: async function () {
    const payload = {
      symbol: String(HMTSTC_APP.state.realOrderSymbol || 'BTCUSDT').toUpperCase(),
      side: String(HMTSTC_APP.state.realOrderSide || 'BUY').toUpperCase(),
      quote_order_qty: Number(String(HMTSTC_APP.state.realOrderAmount || 5).replace(',', '.'))
    };
    const ok = await this.confirmAction({
      title: 'Real Order Dry-run',
      message: payload.symbol + ' için ' + payload.side + ' / ' + payload.quote_order_qty + ' USDT dry-run çalıştırılacak. Binance’e gerçek emir gönderilmez.',
      level: 'warning',
      confirmText: 'Dry-run Çalıştır'
    });
    if (!ok) return;
    try {
      const result = await this.fetchJson('/api/real/orders/dry-run', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
      });
      HMTSTC_DATA.realOrderPreview = result.safety || result;
      await this.auditAction('real_order.dry_run_ui', result.status || 'ok', 'Dry-run real order tamamlandı.', { category: 'trading', severity: 'critical', endpoint: '/api/real/orders/dry-run', payload: payload, result: result });
      await this.syncApiData();
    } catch (error) {
      alert(this.apiErrorMessage(error, 'Real order dry-run başarısız.'));
    }
  },

  placeRealOrderWithPreviewToken: async function () {
    const preview = HMTSTC_DATA.realOrderPreview || {};
    const token = preview.confirmation_token || '';
    const payload = {
      symbol: String(preview.symbol || HMTSTC_APP.state.realOrderSymbol || 'BTCUSDT').toUpperCase(),
      side: String(preview.side || HMTSTC_APP.state.realOrderSide || 'BUY').toUpperCase(),
      quote_order_qty: Number(preview.quote_order_qty || String(HMTSTC_APP.state.realOrderAmount || 5).replace(',', '.')),
      confirmation_token: token
    };
    if (!token) {
      alert('Geçerli confirmation token yok. Önce Preview çalıştır.');
      return;
    }
    const ok = await this.confirmAction({
      title: 'GERÇEK EMİR ONAYI',
      message: 'Bu işlem ancak env real enabled, dry-run off, owner unlock, pilot ve safety kapıları açıksa gerçek Binance emri gönderebilir. Emin misin?',
      level: 'critical',
      confirmText: 'Token ile Gönder'
    });
    if (!ok) return;
    try {
      const result = await this.fetchJson('/api/real/orders/place', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
      });
      await this.auditAction('real_order.place_ui', result.status || 'ok', 'Real order place endpoint sonucu alındı.', { category: 'trading', severity: 'critical', endpoint: '/api/real/orders/place', payload: payload, result: result });
      await this.syncApiData();
    } catch (error) {
      const msg = this.apiErrorMessage(error, 'Gerçek emir gönderimi safety tarafından engellendi veya başarısız oldu.');
      await this.auditAction('real_order.place_ui', 'blocked', msg, { category: 'trading', severity: 'blocked', endpoint: '/api/real/orders/place', payload: payload });
      alert(msg);
    }
  },

  reconcileRealPositions: async function () {
    const ok = await this.confirmAction({
      title: 'Real Position Reconciliation',
      message: 'Binance bakiyesi ile bot real position state karşılaştırılacak. Uyuşmazlık varsa real trade kilitli/review durumuna alınabilir.',
      level: 'warning',
      confirmText: 'Reconcile Et'
    });
    if (!ok) return;
    try {
      const result = await this.fetchJson('/api/real/positions/reconcile', { method: 'POST' });
      await this.auditAction('real_positions.reconcile', result.status || 'ok', 'Real position reconciliation çalıştı.', { category: 'trading', severity: result.status === 'review' ? 'warning' : 'notice', endpoint: '/api/real/positions/reconcile', result: result });
      await this.syncApiData();
    } catch (error) {
      alert(this.apiErrorMessage(error, 'Real position reconciliation başarısız.'));
    }
  },

  previewEmergencyClose: async function () {
    const ok = await this.confirmAction({
      title: 'Emergency Close Preview',
      message: 'Bu işlem gerçek pozisyonları otomatik kapatmaz; owner için dry-run/preview listesi üretir.',
      level: 'critical',
      confirmText: 'Preview Al'
    });
    if (!ok) return;
    try {
      const result = await this.fetchJson('/api/real/positions/emergency-close', { method: 'POST' });
      HMTSTC_DATA.realEmergencyClosePreview = result;
      await this.auditAction('real_positions.emergency_close_preview', result.status || 'preview', 'Emergency close preview üretildi.', { category: 'trading', severity: 'critical', endpoint: '/api/real/positions/emergency-close', result: result });
      this.render();
    } catch (error) {
      alert(this.apiErrorMessage(error, 'Emergency close preview alınamadı.'));
    }
  },

  transitionRealPosition: async function (positionId, toStatus) {
    const ok = await this.confirmAction({
      title: 'Real Position Lifecycle Transition',
      message: 'Bu işlem gerçek pozisyon state bilgisini günceller. Binance emri göndermez; audit kaydı oluşturur.',
      level: 'warning',
      confirmText: 'State Güncelle'
    });
    if (!ok) return;
    try {
      const result = await this.fetchJson('/api/real/positions/transition', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ position_id: positionId, to_status: toStatus, reason: 'manual_ui_transition' })
      });
      await this.auditAction('real_position.transition_ui', result.status || 'ok', 'Real position lifecycle transition tamamlandı.', { category: 'trading', severity: result.status === 'ok' ? 'warning' : 'blocked', endpoint: '/api/real/positions/transition', result: result });
      await this.syncApiData();
    } catch (error) {
      alert(this.apiErrorMessage(error, 'Real position lifecycle transition başarısız.'));
    }
  },

  startRealPilot: async function () {
    const minutes = Number(String(HMTSTC_APP.state.realPilotMinutes || 60).replace(',', '.')) || 60;
    const ok = await this.confirmAction({
      title: 'Mikro Pilot Başlat',
      message: 'Mikro pilot gerçek para hazırlık modudur. Sadece owner, safety, pilot limitleri ve lock politikası ile çalışır. Pilot bitince sistem otomatik kilitlenir.',
      level: 'critical',
      confirmText: 'Mikro Pilotu Başlat'
    });
    if (!ok) return;
    try {
      const result = await this.fetchJson('/api/real/pilot/start', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ minutes: minutes })
      });
      await this.auditAction('real_pilot.start_ui', result.status || 'ok', 'Mikro pilot UI üzerinden başlatıldı.', { category: 'trading', severity: 'critical', endpoint: '/api/real/pilot/start', result: result });
      await this.syncApiData();
    } catch (error) {
      const msg = this.apiErrorMessage(error, 'Mikro pilot başlatılamadı.');
      await this.auditAction('real_pilot.start_ui', 'blocked', msg, { category: 'trading', severity: 'blocked', endpoint: '/api/real/pilot/start' });
      alert(msg);
    }
  },

  stopRealPilot: async function () {
    const ok = await this.confirmAction({
      title: 'Mikro Pilot Durdur',
      message: 'Pilot kapatılacak ve real trading owner unlock güvenli moda kilitlenecek.',
      level: 'critical',
      confirmText: 'Pilotu Durdur ve Kilitle'
    });
    if (!ok) return;
    try {
      const result = await this.fetchJson('/api/real/pilot/stop', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ reason: 'manual_ui_stop' })
      });
      await this.auditAction('real_pilot.stop_ui', result.status || 'ok', 'Mikro pilot UI üzerinden durduruldu.', { category: 'trading', severity: 'critical', endpoint: '/api/real/pilot/stop', result: result });
      await this.syncApiData();
    } catch (error) {
      alert(this.apiErrorMessage(error, 'Mikro pilot durdurulamadı.'));
    }
  },

  refreshPilotReport: async function () {
    try {
      const result = await this.fetchJson('/api/real/pilot/report');
      HMTSTC_DATA.realPilotReport = result;
      await this.auditAction('real_pilot.report_ui', 'ok', 'Mikro pilot raporu yenilendi.', { category: 'trading', severity: 'notice', endpoint: '/api/real/pilot/report' });
      this.render();
    } catch (error) {
      alert(this.apiErrorMessage(error, 'Mikro pilot raporu alınamadı.'));
    }
  },

  triggerEmergencyLock: async function () {
    const ok = await this.confirmAction({
      title: 'Emergency Lock',
      message: 'Real trading owner unlock kapatılır, mikro pilot durdurulur ve sistem güvenli moda alınır. Bu işlem gerçek pozisyonları otomatik kapatmaz.',
      level: 'critical',
      confirmText: 'Emergency Lock'
    });
    if (!ok) return;
    try {
      const result = await this.fetchJson('/api/real/emergency/lock', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ reason: 'manual_ui_emergency_lock' })
      });
      HMTSTC_DATA.realEmergencyRecovery = result;
      await this.auditAction('emergency.lock_ui', result.status || 'ok', 'Emergency lock UI üzerinden aktif edildi.', { category: 'trading', severity: 'critical', endpoint: '/api/real/emergency/lock', result: result });
      await this.syncApiData();
    } catch (error) {
      alert(this.apiErrorMessage(error, 'Emergency lock çalıştırılamadı.'));
    }
  },

  refreshEmergencyChecklist: async function () {
    try {
      const result = await this.fetchJson('/api/real/emergency/checklist');
      HMTSTC_DATA.realEmergencyChecklist = result;
      await this.auditAction('emergency.checklist_ui', 'ok', 'Emergency recovery checklist yenilendi.', { category: 'trading', severity: 'notice', endpoint: '/api/real/emergency/checklist' });
      this.render();
    } catch (error) {
      alert(this.apiErrorMessage(error, 'Emergency checklist alınamadı.'));
    }
  },

  unlockEmergencyRecovery: async function () {
    const ok = await this.confirmAction({
      title: 'Recovery Unlock',
      message: 'Emergency recovery kilidi sadece checklist yeterliyse kaldırılır. Bu işlem botu veya real trading owner unlock’u otomatik başlatmaz.',
      level: 'critical',
      confirmText: 'Recovery Unlock Dene'
    });
    if (!ok) return;
    try {
      const result = await this.fetchJson('/api/real/emergency/recovery-unlock', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ reason: 'manual_ui_recovery_unlock' })
      });
      HMTSTC_DATA.realEmergencyRecovery = result;
      await this.auditAction('emergency.recovery_unlock_ui', result.status || 'ok', 'Emergency recovery unlock denendi.', { category: 'trading', severity: 'critical', endpoint: '/api/real/emergency/recovery-unlock', result: result });
      await this.syncApiData();
    } catch (error) {
      const msg = this.apiErrorMessage(error, 'Recovery unlock checklist tarafından engellendi.');
      await this.auditAction('emergency.recovery_unlock_ui', 'blocked', msg, { category: 'trading', severity: 'blocked', endpoint: '/api/real/emergency/recovery-unlock' });
      alert(msg);
    }
  }

};


// Rev99 operator-free Summary control preview. Explicit owner click only; no auto-execute.
window.HMTSTC_APP_REAL_TRADE = window.HMTSTC_APP_REAL_TRADE || {};
window.HMTSTC_APP_REAL_TRADE.operatorControlPreview = async function (controlKey, endpoint) {
  const label = controlKey === 'emergency_stop' ? 'Emergency Stop' : (controlKey === 'safe_mode' ? 'Safe Mode' : controlKey);
  this.set({
    confirmModal: {
      open: true,
      level: controlKey === 'emergency_stop' ? 'critical' : 'warning',
      title: label,
      message: label + ' explicit owner kontrolüdür. Emir göndermez; yalnızca güvenlik kilidi/safe-mode akışını tetikler.',
      confirmText: 'Uygula',
      cancelText: 'Vazgeç',
      onConfirm: async () => {
        this.set({ confirmModal: null });
        try {
          await this.fetchJson(endpoint || '/api/real/lock', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ reason: 'rev99_operator_free_dashboard_' + controlKey })
          });
          await this.syncNow();
        } catch (error) {
          this.set({ toast: (error && (error.userMessage || error.message)) || 'Operator kontrol uygulanamadı.' });
        }
      },
      onCancel: () => this.set({ confirmModal: null })
    }
  });
};
