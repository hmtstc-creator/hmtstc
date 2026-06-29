window.HMTSTC_APP_AUTH = {
  restoreAuth: async function () {
    const token = localStorage.getItem("hmtstc_token") || "";

    HMTSTC_APP.state.authDiagnostics = Object.assign({}, HMTSTC_APP.state.authDiagnostics || {}, {
      tokenExists: Boolean(token),
      lastRestoreAt: new Date().toLocaleTimeString("tr-TR"),
      lastBlockReason: token ? "auth_restore_pending" : "no_token"
    });

    if (!token) {
      HMTSTC_APP.state.auth = false;
      HMTSTC_APP.state.token = null;
      HMTSTC_APP.state.user = null;
      HMTSTC_APP.state.authRestorePending = false;
      HMTSTC_APP.state.authRestoreChecked = true;
      HMTSTC_APP.state.authRestoreError = "";
      HMTSTC_APP.state.lastSyncBlockReason = "no_token";
      return false;
    }

    HMTSTC_APP.state.auth = false;
    HMTSTC_APP.state.token = token;
    HMTSTC_APP.state.authRestorePending = true;
    HMTSTC_APP.state.authRestoreChecked = false;
    HMTSTC_APP.state.authRestoreError = "";

    try {
      const result = await HMTSTC_APP.fetchJson("/api/auth/me", {
        requestKind: "auth_restore",
        preventGlobalAbort: true,
        timeoutMs: 10000
      });
      const userPayload = result.user && typeof result.user === "object" ? result.user : result;
      const username = result.username || userPayload.username || localStorage.getItem("hmtstc_user") || "default";
      const role = result.role || userPayload.role || localStorage.getItem("hmtstc_role") || "user";

      localStorage.setItem("hmtstc_user", username);
      localStorage.setItem("hmtstc_role", role);
      localStorage.setItem("hmtstc_force_password_change", result.force_password_change || userPayload.force_password_change ? "true" : "false");

      HMTSTC_APP.state.auth = true;
      HMTSTC_APP.state.token = token;
      HMTSTC_APP.state.user = username;
      HMTSTC_APP.state.role = role;
      HMTSTC_APP.state.forcePasswordChange = Boolean(result.force_password_change || userPayload.force_password_change);
      HMTSTC_APP.state.loginError = "";
      HMTSTC_APP.state.authRestorePending = false;
      HMTSTC_APP.state.authRestoreChecked = true;
      HMTSTC_APP.state.authRestoreError = "";
      HMTSTC_APP.state.heavySyncAllowedAtMs = Date.now() + 120000;
      HMTSTC_APP.state.authDiagnostics = Object.assign({}, HMTSTC_APP.state.authDiagnostics || {}, {
        tokenExists: true,
        authMeStatus: 200,
        lastRestoreAt: new Date().toLocaleTimeString("tr-TR"),
        lastBlockReason: ""
      });

      if (!HMTSTC_APP.state.forcePasswordChange) {
        await HMTSTC_APP.syncApiData({ skipHeavySync: true });
      }

      return true;
    } catch (error) {
      const type = error && error.apiErrorType;
      const status = error && error.status;

      HMTSTC_APP.state.auth = false;
      HMTSTC_APP.state.authRestorePending = false;
      HMTSTC_APP.state.authRestoreChecked = true;
      HMTSTC_APP.state.apiReady = false;
      HMTSTC_APP.state.apiSyncReady = false;

      if (type === "http_401" || type === "http_403" || status === 401 || status === 403) {
        localStorage.removeItem("hmtstc_user");
        localStorage.removeItem("hmtstc_token");
        localStorage.removeItem("hmtstc_role");
        localStorage.removeItem("hmtstc_force_password_change");

        if (HMTSTC_APP.clearRestrictedData) {
          HMTSTC_APP.clearRestrictedData({ preserveRules: true });
        }

        HMTSTC_APP.state.token = null;
        HMTSTC_APP.state.user = null;
        HMTSTC_APP.state.role = "user";
        HMTSTC_APP.state.forcePasswordChange = false;
        HMTSTC_APP.state.loginError = "Oturum süresi doldu, tekrar giriş yap.";
        HMTSTC_APP.state.authRestoreError = "";
        HMTSTC_APP.state.lastSyncBlockReason = "auth_401";
        HMTSTC_APP.state.authDiagnostics = Object.assign({}, HMTSTC_APP.state.authDiagnostics || {}, {
          tokenExists: false,
          authMeStatus: status || 401,
          lastRestoreAt: new Date().toLocaleTimeString("tr-TR"),
          lastBlockReason: "auth_401"
        });
      } else {
        HMTSTC_APP.state.token = token;
        HMTSTC_APP.state.user = null;
        HMTSTC_APP.state.loginError = "Auth doğrulama geçici olarak yapılamadı. Tekrar giriş yapabilirsin.";
        HMTSTC_APP.state.authRestoreError = "Auth doğrulama geçici olarak yapılamadı.";
        HMTSTC_APP.state.lastSyncBlockReason = "auth_restore_network_error";
        HMTSTC_APP.state.authDiagnostics = Object.assign({}, HMTSTC_APP.state.authDiagnostics || {}, {
          tokenExists: true,
          authMeStatus: status || null,
          lastRestoreAt: new Date().toLocaleTimeString("tr-TR"),
          lastBlockReason: "auth_restore_network_error"
        });
      }

      return false;
    }
  },

  login: async function () {
    if (HMTSTC_APP.state.loginInProgress) {
      return;
    }

    const usernameInput = document.getElementById("login-username");
    const passwordInput = document.getElementById("login-password");
    const username = usernameInput ? usernameInput.value.trim() : "";
    const password = passwordInput ? passwordInput.value.trim() : "";

    if (!username || !password) {
      HMTSTC_APP.set({ loginError: "Kullanıcı adı ve şifre gerekli." });
      return;
    }

    HMTSTC_APP.state.loginInProgress = true;
    HMTSTC_APP.state.loginError = "";
    HMTSTC_APP.render();

    try {
      const result = await HMTSTC_APP.fetchJson("/api/auth/login", {
        method: "POST",
        requestKind: "mutation",
        preventGlobalAbort: true,
        timeoutMs: 15000,
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ username: username, password: password })
      });

      if (!result.authenticated || !result.token) {
        localStorage.removeItem("hmtstc_user");
        localStorage.removeItem("hmtstc_token");
        localStorage.removeItem("hmtstc_role");
        localStorage.removeItem("hmtstc_force_password_change");

        const authStoreError = result.status === "auth_store_error";
        HMTSTC_APP.set({
          auth: false,
          token: null,
          authRestorePending: false,
          authRestoreChecked: true,
          authRestoreError: "",
          apiReady: false,
          apiSyncReady: false,
          loginError: authStoreError
            ? (result.message || "Oturum başlatılamadı. Lütfen tekrar deneyin.")
            : (result.message || "Giriş başarısız.")
        });
        return;
      }

      localStorage.setItem("hmtstc_user", result.username);
      localStorage.setItem("hmtstc_token", result.token);
      localStorage.setItem("hmtstc_role", result.role || "user");
      localStorage.setItem("hmtstc_force_password_change", result.force_password_change ? "true" : "false");

      HMTSTC_APP.clearRestrictedData();
      HMTSTC_APP.state.auth = true;
      HMTSTC_APP.state.user = result.username;
      HMTSTC_APP.state.token = result.token;
      HMTSTC_APP.state.role = result.role || "user";
      HMTSTC_APP.state.forcePasswordChange = Boolean(result.force_password_change);
      HMTSTC_APP.state.authRestorePending = false;
      HMTSTC_APP.state.authRestoreChecked = true;
      HMTSTC_APP.state.authRestoreError = "";
      HMTSTC_APP.state.loginError = "";
      HMTSTC_APP.state.page = "dashboard";
      HMTSTC_APP.state.settingsLoaded = false;
      HMTSTC_APP.state.coinFilterDraft = null;
      HMTSTC_APP.state.coinFilterDirty = false;
      HMTSTC_APP.state.strategyDirty = false;
      HMTSTC_APP.state.strategySaving = false;
      HMTSTC_APP.state.syncInProgress = false;
      HMTSTC_APP.state.heavySyncInProgress = false;
      HMTSTC_APP.state.heavySyncAllowedAtMs = Date.now() + 120000;
      HMTSTC_APP.state.lastHeavySyncMs = 0;
      HMTSTC_APP.state.authDiagnostics = Object.assign({}, HMTSTC_APP.state.authDiagnostics || {}, {
        tokenExists: true,
        authMeStatus: null,
        lastRestoreAt: new Date().toLocaleTimeString("tr-TR"),
        lastBlockReason: ""
      });

      if (HMTSTC_APP.state.forcePasswordChange) {
        HMTSTC_APP.render();
        return;
      }

      await HMTSTC_APP.syncApiData({ skipHeavySync: true });
      HMTSTC_APP.render();
    } catch (error) {
      console.error("Login hatası:", error);
      localStorage.removeItem("hmtstc_user");
      localStorage.removeItem("hmtstc_token");
      localStorage.removeItem("hmtstc_role");
      localStorage.removeItem("hmtstc_force_password_change");
      HMTSTC_APP.set({
        auth: false,
        token: null,
        authRestorePending: false,
        authRestoreChecked: true,
        loginError: HMTSTC_APP.apiErrorMessage ? HMTSTC_APP.apiErrorMessage(error, "Backend bağlantısı kurulamadı.") : "Backend bağlantısı kurulamadı."
      });
    } finally {
      HMTSTC_APP.state.loginInProgress = false;
      HMTSTC_APP.render();
    }
  },

  changeOwnPassword: async function () {
    const newInput = document.getElementById("new-password");
    const confirmInput = document.getElementById("new-password-confirm");
    const newPassword = newInput ? newInput.value.trim() : "";
    const confirmPassword = confirmInput ? confirmInput.value.trim() : "";

    if (!newPassword || newPassword.length < 6) {
      HMTSTC_APP.set({ loginError: "Yeni şifre en az 6 karakter olmalı." });
      return;
    }
    if (newPassword !== confirmPassword) {
      HMTSTC_APP.set({ loginError: "Şifreler aynı değil." });
      return;
    }

    try {
      const result = await HMTSTC_APP.fetchJson("/api/auth/change-password", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ new_password: newPassword })
      });
      if (result.changed) {
        localStorage.setItem("hmtstc_force_password_change", "false");
        HMTSTC_APP.state.forcePasswordChange = false;
        HMTSTC_APP.state.loginError = "";
        await HMTSTC_APP.syncApiData({ skipHeavySync: true });
        HMTSTC_APP.render();
      } else {
        HMTSTC_APP.set({ loginError: result.message || "Şifre değiştirilemedi." });
      }
    } catch (error) {
      console.error(error);
      HMTSTC_APP.set({ loginError: "Şifre değiştirme isteği başarısız." });
    }
  },

  logout: async function () {
    const app = window.HMTSTC_APP || null;
    const state = app && app.state ? app.state : {};

    try {
      if (state.token && app && app.fetchJson) {
        await app.fetchJson("/api/auth/logout", {
          method: "POST",
          requestKind: "mutation",
          preventGlobalAbort: true,
          timeoutMs: 15000,
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({})
        });
      }
    } catch (error) {
      if (!error || error.status !== 401) {
        console.warn("Logout hatası (ignore):", error);
      }
    }

    localStorage.removeItem("hmtstc_user");
    localStorage.removeItem("hmtstc_token");
    localStorage.removeItem("hmtstc_role");
    localStorage.removeItem("hmtstc_force_password_change");

    if (app && app.clearRestrictedData) {
      app.clearRestrictedData({ preserveRules: true });
    }

    if (app) {
      app.state = app.state || {};
      app.state.auth = false;
      app.state.user = null;
      app.state.role = "user";
      app.state.forcePasswordChange = false;
      app.state.token = null;
      app.state.authRestorePending = false;
      app.state.authRestoreChecked = true;
      app.state.authRestoreError = "";
      app.state.page = "dashboard";
      app.state.loginError = "";
      app.state.settingsLoaded = false;
      app.state.syncInProgress = false;
      app.state.heavySyncInProgress = false;
      app.state.heavySyncAllowedAtMs = null;
      app.state.lastHeavySyncMs = 0;
      app.state.apiReady = false;
      app.state.apiSyncReady = false;
      app.state.lastSyncBlockReason = "no_token";
      app.state.authDiagnostics = Object.assign({}, app.state.authDiagnostics || {}, {
        tokenExists: false,
        authMeStatus: null,
        lastRestoreAt: new Date().toLocaleTimeString("tr-TR"),
        lastBlockReason: "no_token"
      });

      if (app.render) app.render();
    } else {
      window.location.hash = "#login";
    }
  },

  renderPasswordChange: function () {
    return '<div class="login">' +
      '<div class="login-box premium-login-box">' +
        '<div class="login-mark">🔐</div>' +
        '<h2>Yeni Şifre Belirle</h2>' +
        '<p class="login-note">Hesabın sıfırlandı. Devam etmek için yeni şifre oluştur.</p>' +
        '<div class="login-field">🔑<input id="new-password" type="password" placeholder="Yeni şifre" autocomplete="new-password"></div>' +
        '<div class="login-field">✅<input id="new-password-confirm" type="password" placeholder="Yeni şifre tekrar" autocomplete="new-password" onkeydown="if(event.key===&quot;Enter&quot;){HMTSTC_APP.changeOwnPassword()}"></div>' +
        (HMTSTC_APP.state.loginError ? '<div class="login-error">' + HMTSTC_APP.escapeHtml(HMTSTC_APP.state.loginError) + '</div>' : '') +
        '<button class="btn btn-main" style="width:100%" onclick="HMTSTC_APP.changeOwnPassword()">Şifreyi Değiştir</button>' +
        '<button class="btn btn-ghost" style="width:100%;margin-top:10px" onclick="HMTSTC_APP.logout()">Çıkış</button>' +
      '</div>' +
    '</div>';
  },

  renderLogin: function () {
    const loginInProgress = Boolean(HMTSTC_APP.state.loginInProgress);
    return '<div class="login">' +
      '<div class="login-box premium-login-box">' +
        '<div class="login-mark">H</div>' +
        '<h2>HMTSTC Giriş</h2>' +
        '<p class="login-note">Private trading lab erişimi.</p>' +
        '<div class="login-field">👤<input id="login-username" placeholder="Kullanıcı adı" autocomplete="username"></div>' +
        '<div class="login-field">🔑<input id="login-password" type="password" placeholder="Şifre" autocomplete="current-password" onkeydown="if(event.key===&quot;Enter&quot; && !HMTSTC_APP.state.loginInProgress){HMTSTC_APP.login()}"></div>' +
        (HMTSTC_APP.state.loginError ? '<div class="login-error">' + HMTSTC_APP.escapeHtml(HMTSTC_APP.state.loginError) + '</div>' : '') +
        '<button class="btn btn-main" style="width:100%" ' + (loginInProgress ? "disabled " : "") + 'onclick="HMTSTC_APP.login()">' +
          (loginInProgress ? "Giriş yapılıyor..." : "Giriş") +
        '</button>' +
      '</div>' +
    '</div>';
  }
};
