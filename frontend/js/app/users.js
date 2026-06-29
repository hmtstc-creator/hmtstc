/*
 * Users feature glue layer.
 * Some buttons/pages call methods under HMTSTC_APP namespace.
 */

window.HMTSTC_APP_USERS = {
  createUserFromForm: async function () {
    const username = ((document.getElementById('new-user-name') || {}).value || '').trim();
    const password = ((document.getElementById('new-user-password') || {}).value || '').trim();
    const role = ((document.getElementById('new-user-role') || {}).value || 'user').trim();
    if (!username || password.length < 6) {
      HMTSTC_DATA.usersMessage = 'Kullanıcı adı gerekli; şifre en az 6 karakter olmalı.';
      this.render();
      return;
    }
    try {
      await this.fetchJson('/api/users', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ username: username, password: password, role: role })
      });
      HMTSTC_DATA.usersMessage = 'Kullanıcı oluşturuldu.';
      await this.auditAction('user_create', 'ok', username, { role: role });
      HMTSTC_APP.state.usersLoaded = false;
      ['new-user-name', 'new-user-password'].forEach(function (id) {
        const element = document.getElementById(id);
        if (element) element.value = '';
      });
      if (document.activeElement && document.activeElement.blur) document.activeElement.blur();
      await this.syncUsersData();
      this.render();
    } catch (e) {
      HMTSTC_DATA.usersMessage = this.apiErrorMessage(e, 'Kullanıcı oluşturulamadı.');
      await this.auditAction('user_create', 'error', HMTSTC_DATA.usersMessage, { username: username });
      if (document.activeElement && document.activeElement.blur) document.activeElement.blur();
      HMTSTC_APP.state.usersLoaded = false;
      await this.syncUsersData();
      this.render();
    }
  },

  refreshUsersList: async function () {
    HMTSTC_DATA.usersMessage = 'Kullanıcı listesi yenileniyor.';
    HMTSTC_APP.state.usersLoaded = false;
    HMTSTC_APP.state.usersLoading = true;
    if (document.activeElement && document.activeElement.blur) document.activeElement.blur();
    await this.syncUsersData();
    this.render();
  },

  resetUserPasswordFromForm: async function (username) {
    const input = document.getElementById('reset-pass-' + encodeURIComponent(username)) || document.getElementById('reset-pass-' + username);
    const password = input ? input.value.trim() : '';
    if (password.length < 6) {
      HMTSTC_DATA.usersMessage = 'Yeni şifre en az 6 karakter olmalı.';
      this.render();
      return;
    }
    try {
      await this.fetchJson('/api/users/' + encodeURIComponent(username) + '/reset-password', {
        method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ password: password })
      });
      HMTSTC_DATA.usersMessage = username + ' şifresi sıfırlandı.';
      HMTSTC_APP.state.usersLoaded = false;
      await this.auditAction('user_reset_password', 'ok', username, { username: username });
      if (input) input.value = '';
      if (document.activeElement && document.activeElement.blur) document.activeElement.blur();
      await this.syncUsersData();
      this.render();
    } catch (e) {
      HMTSTC_DATA.usersMessage = this.apiErrorMessage(e, 'Şifre sıfırlanamadı.');
      await this.auditAction('user_reset_password', 'error', HMTSTC_DATA.usersMessage, { username: username });
      this.render();
    }
  },

  setUserActive: async function (username, active) {
    if (username === this.state.user && active === false) {
      HMTSTC_DATA.usersMessage = 'Kendi hesabını pasife alamazsın.';
      this.render();
      return;
    }
    if (active === false && !confirm(username + ' pasife alınsın mı?')) {
      return;
    }
    try {
      await this.fetchJson('/api/users/' + encodeURIComponent(username) + '/active', {
        method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ active: active })
      });
      await this.auditAction('user_active_toggle', 'ok', username, { username: username, active: active });
      HMTSTC_APP.state.usersLoaded = false;
      await this.syncUsersData();
      this.render();
    } catch (e) {
      HMTSTC_DATA.usersMessage = this.apiErrorMessage(e, 'Kullanıcı durumu değiştirilemedi.');
      await this.auditAction('user_active_toggle', 'error', HMTSTC_DATA.usersMessage, { username: username, active: active });
      this.render();
    }
  }
};

Object.assign(window.HMTSTC_APP_USERS, {
  saveMyApiConnectionFromForm: async function () {
    const exchange = ((document.getElementById('my-api-exchange') || {}).value || 'binance').trim();
    const environment = ((document.getElementById('my-api-environment') || {}).value || 'testnet').trim();
    const apiKey = ((document.getElementById('my-api-key') || {}).value || '').trim();
    const apiSecret = ((document.getElementById('my-api-secret') || {}).value || '').trim();
    const tradeEnabled = Boolean((document.getElementById('my-api-trade-enabled') || {}).checked);
    const mainnetConfirmText = ((document.getElementById('my-api-mainnet-confirm') || {}).value || '').trim();
    if (!apiKey || !apiSecret) {
      HMTSTC_DATA.usersMessage = 'API key ve secret gerekli.';
      this.render();
      return;
    }
    try {
      await this.fetchJson('/api/users/me/api-connection', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          exchange: exchange,
          environment: environment,
          testnet: environment !== 'live',
          api_key: apiKey,
          secret_key: apiSecret,
          mainnet_ack: environment === 'live' && mainnetConfirmText.length > 0,
          mainnet_confirm_text: mainnetConfirmText,
          permissions: { read: true, trade: tradeEnabled },
          trade_enabled: tradeEnabled
        })
      });
      HMTSTC_DATA.usersMessage = 'API bağlantısı kaydedildi. Secret açık şekilde geri gösterilmez.';
      await this.syncApiData();
    } catch (e) {
      HMTSTC_DATA.usersMessage = this.apiErrorMessage(e, 'API bağlantısı kaydedilemedi.');
      this.render();
    }
  },

  deleteMyApiConnection: async function () {
    if (!confirm('API bağlantısı silinsin mi?')) return;
    try {
      await this.fetchJson('/api/users/me/api-connection', { method: 'DELETE' });
      HMTSTC_DATA.usersMessage = 'API bağlantısı silindi.';
      await this.syncApiData();
    } catch (e) {
      HMTSTC_DATA.usersMessage = this.apiErrorMessage(e, 'API bağlantısı silinemedi.');
      this.render();
    }
  }
});

