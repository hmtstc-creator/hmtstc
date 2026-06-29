window.HMTSTC_PAGES = window.HMTSTC_PAGES || {};

window.HMTSTC_PAGES.users = function () {
  const role = String((HMTSTC_APP.state || {}).role || localStorage.getItem("hmtstc_role") || "user").trim().toLowerCase();
  const payload = HMTSTC_DATA.usersPayload || {};

  const hasUsers = Array.isArray(payload.users) && payload.users.length > 0;
  const shouldLoadUsers = role === "owner" && !HMTSTC_APP.state.usersLoaded && !HMTSTC_APP.state.usersLoading && !hasUsers && payload.status !== "error";

  if (shouldLoadUsers) {
    HMTSTC_APP.state.usersLoading = true;
    setTimeout(function () {
      if (!HMTSTC_APP.syncUsersData) return;
      HMTSTC_APP.syncUsersData().then(function () {
        HMTSTC_APP.render();
      });
    }, 0);
  }

  const users = payload.users || [];
  const msg = HMTSTC_DATA.usersMessage || payload.message || '';
  function esc(v) { return HMTSTC_APP.escapeHtml(v === undefined || v === null ? '' : v); }
  function jsArg(v) { return JSON.stringify(String(v === undefined || v === null ? '' : v)); }

  const rows = users.map(function (u) {
    const username = String(u.username || '');
    const resetId = 'reset-pass-' + encodeURIComponent(username);
    const usernameArg = jsArg(username);
    return '<tr>' +
      '<td><b>' + esc(u.username) + '</b><br><small>' + esc(u.created_at || '-') + '</small></td>' +
      '<td>' + esc(u.role || 'user') + '</td>' +
      '<td>' + (u.active === false ? '<span class="negative">Pasif</span>' : '<span class="positive">Aktif</span>') + '</td>' +
      '<td>' + (u.force_password_change ? '<span class="status-pill status-warn">Şifre değiştirmeli</span>' : '<span class="status-pill status-ok">Normal</span>') + '</td>' +
      '<td>' + esc(u.last_login_at || '-') + '</td>' +
      '<td><input id="' + esc(resetId) + '" class="compact-input" placeholder="Yeni şifre"><button class="btn btn-ghost btn-small" onclick="HMTSTC_APP.resetUserPasswordFromForm(' + usernameArg + ')">Sıfırla</button> ' +
      (u.active === false ? '<button class="btn btn-ghost btn-small" onclick="HMTSTC_APP.setUserActive(' + usernameArg + ', true)">Aktif Et</button>' : '<button class="btn btn-ghost btn-small danger-outline" onclick="HMTSTC_APP.setUserActive(' + usernameArg + ', false)">Pasif Et</button>') + '</td>' +
    '</tr>';
  }).join('');

  return '<div class="operation-page users-page">' +
    (msg ? '<div class="inline-alert info"><b>Bilgi</b><span>' + esc(msg) + '</span></div>' : '') +
    HMTSTC_UI.card('<div class="section-title"><span>Yeni Kullanıcı</span><small>İlk girişte şifre değiştirme zorunlu olur</small></div>' +
      '<div class="user-create-grid"><input id="new-user-name" placeholder="Kullanıcı adı"><input id="new-user-password" placeholder="İlk şifre"><select id="new-user-role"><option value="user">user</option><option value="admin">admin</option></select><button class="btn btn-main" onclick="HMTSTC_APP.createUserFromForm()">Kullanıcı Oluştur</button></div>', 'ops-panel') +
    HMTSTC_UI.card('<div class="section-title"><span>Kullanıcı Listesi</span><small>' + (HMTSTC_APP.state.usersLoading ? 'yükleniyor' : users.length + ' kayıt') + '</small></div><div class="buttons compact-buttons"><button class="btn btn-ghost btn-small" onclick="HMTSTC_APP.refreshUsersList()">Listeyi Yenile</button></div><div class="table-wrap"><table><thead><tr><th>Kullanıcı</th><th>Rol</th><th>Durum</th><th>Şifre</th><th>Son Giriş</th><th>İşlem</th></tr></thead><tbody>' + (rows || '<tr><td colspan="6">' + (HMTSTC_APP.state.usersLoading ? 'Kullanıcı listesi yükleniyor...' : 'Henüz kullanıcı yok.') + '</td></tr>') + '</tbody></table></div>', 'ops-panel') +
  '</div>';
};
