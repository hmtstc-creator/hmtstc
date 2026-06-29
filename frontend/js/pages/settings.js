window.HMTSTC_PAGES = window.HMTSTC_PAGES || {};

window.HMTSTC_PAGES.settings = function () {
  const settings = HMTSTC_APP.getSettings ? HMTSTC_APP.getSettings() : (HMTSTC_DATA.settings || {});
  const bot = (settings.bot || {});
  const risk = (settings.risk || {});

  const u = window.HMTSTC_REV58 || {
    esc: function (v) { return HMTSTC_APP.escapeHtml(v === undefined || v === null ? '' : v); },
    card: function (t, st, body, cls) {
      return HMTSTC_UI.card(
        '<div class="section-title"><span>' + this.esc(t) + '</span><small>' + this.esc(st || '') + '</small></div>' + body,
        'ops-panel rev58-panel ' + (cls || '')
      );
    }
  };

  function field(title, desc, value, path, type, placeholder) {
    const input = type === 'select'
      ? '<select data-settings-path="' + u.esc(path) + '"><option value="shadow" ' + (value === 'shadow' ? 'selected' : '') + '>shadow</option><option value="paper" ' + (value === 'paper' ? 'selected' : '') + '>paper</option><option value="disabled" ' + (value === 'disabled' ? 'selected' : '') + '>disabled</option></select>'
      : '<input data-settings-path="' + u.esc(path) + '" data-type="' + (type === 'number' ? 'number' : 'string') + '" value="' + u.esc(value) + '" placeholder="' + u.esc(placeholder || '') + '">';

    return '<label class="field pro-setting-row rev58-setting-field"><div class="pro-setting-info"><span>' + u.esc(title) + '</span><small>' + u.esc(desc || '') + '</small></div><div class="pro-setting-value">' + input + '</div></label>';
  }

  return '' +
    '<div class="rev58-page settings-general-page">' +
      '<div class="grid two-cols rev58-layout-grid">' +
        u.card('Bot İşlem Ayarları', 'Canlı botun pozisyon ve bütçe limitleri.',
          field('Max Açık Pozisyon', 'Aynı anda izin verilen açık pozisyon sayısı.', bot.max_open_positions || 5, 'bot.max_open_positions', 'number') +
          field('USDT / Pozisyon', 'Tek canlı pozisyon için varsayılan büyüklük.', bot.usdt_per_position || 200, 'bot.usdt_per_position', 'number') +
          field('Bot Bütçesi USDT', 'Canlı bot için ayrılan takip bütçesi.', bot.allocated_usdt || 1000, 'bot.allocated_usdt', 'number') +
          field('Maksimum Aynı Yön Pozisyon', 'Aynı yönde açılabilecek pozisyon sınırı.', risk.max_same_direction_positions || 3, 'risk.max_same_direction_positions', 'number')
        ) +
      '</div>' +
      '<div class="grid two-cols rev58-layout-grid">' +
        u.card('Risk Limitleri', 'İşlem açmadan önce korunacak temel risk sınırları.',
          field('Günlük Zarar Limiti', 'USDT bazlı günlük maksimum zarar limiti.', risk.daily_loss_limit || 30, 'risk.daily_loss_limit', 'number') +
          field('Haftalık Zarar Limiti', 'USDT bazlı haftalık maksimum zarar limiti.', risk.weekly_loss_limit || 90, 'risk.weekly_loss_limit', 'number') +
          field('Stop Loss %', 'İşlem başına stop loss yüzdesi.', risk.stop_loss || 0.75, 'risk.stop_loss', 'number') +
          field('Kar Hedefi %', 'İşlem başına hedef kar yüzdesi.', risk.take_profit || 2, 'risk.take_profit', 'number') +
          field('Pozisyon Risk %', 'Her pozisyon için maksimum risk yüzdesi.', risk.risk_per_position_percent || 1, 'risk.risk_per_position_percent', 'number')
        ) +
        u.card('Save', '',
          '<div class="pro-save-bar rev58-save-bar"><span>Genel ayarları kontrol et ve kaydet.</span><div class="actions-inline"><button class="btn btn-main" onclick="HMTSTC_APP.saveSettings()">Ayarları Kaydet</button></div></div>'
        ) +
      '</div>' +
    '</div>';
};

