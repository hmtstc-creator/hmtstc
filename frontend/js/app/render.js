window.HMTSTC_APP_RENDER = {
  page: function () {
    const pageName = HMTSTC_APP.state.page;

    if (!HMTSTC_APP.hasPageAccess(pageName)) {
      HMTSTC_APP.state.page = "dashboard";
      return HMTSTC_PAGES.dashboard();
    }

    if (HMTSTC_PAGES[pageName]) {
      return HMTSTC_PAGES[pageName]();
    }

    console.warn("Unknown/missing page render:", pageName, "Available:", Object.keys(HMTSTC_PAGES || {}));

    HMTSTC_APP.state.page = "dashboard";
    return HMTSTC_PAGES.dashboard();
  },

  escapeHtml: function (value) {
    return String(value || "")
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#039;");
  },

  hasRoleAccess: function (requiredRole) {
    const stateUser = String((HMTSTC_APP.state || {}).user || "").toLowerCase();

    if (String(requiredRole || "").toLowerCase() === "ahmet") {
      return stateUser === "ahmet";
    }

    const role = String((HMTSTC_APP.state || {}).role || "user").toLowerCase();
    const isAhmetOwner = stateUser === "ahmet";

    if (!requiredRole) {
      return true;
    }

    if (Array.isArray(requiredRole)) {
      return requiredRole.some(function (item) {
        return HMTSTC_APP.hasRoleAccess(item);
      });
    }

    const required = String(requiredRole || "").toLowerCase();

    if (required === "owner") {
      return isAhmetOwner || role === "owner";
    }

    if (required === "admin") {
      return isAhmetOwner || role === "owner" || role === "admin";
    }

    if (required === "user") {
      return true;
    }

    return false;
  },

  hasPageAccess: function (pageName) {
    const item = (HMTSTC_DATA.menu || []).find(function (entry) {
      return entry[0] === pageName;
    });

    if (!item) {
      return false;
    }

    return HMTSTC_APP.hasRoleAccess(item[2]);
  },

  renderModal: function () {
    if (!HMTSTC_APP.state.modal) {
      return "";
    }

    return (
      '<div class="modal">' +
        '<div class="modal-box">' +
          '<h2>Acil Durdur</h2>' +
          '<p>Canlı bot durdurulur. Seçilen aksiyona göre pozisyonlar korunur veya kapatılır.</p>' +

          '<div class="list">' +
            '<button class="panel" onclick="HMTSTC_APP.emergencyStop(\'stop_new_buys\')">' +
              '<strong>Yeni alımları durdur</strong>' +
              '<span>Açık pozisyonlar korunur.</span>' +
            '</button>' +

            '<button class="panel" onclick="HMTSTC_APP.emergencyStop(\'keep_positions\')">' +
              '<strong>Botu durdur, pozisyonları bırak</strong>' +
              '<span>Açık pozisyonlar takipte kalır.</span>' +
            '</button>' +

            '<button class="panel" onclick="HMTSTC_APP.emergencyStop(\'close_all_shadow\')">' +
              '<strong>Tüm açık pozisyonları kapat</strong>' +
              '<span>Açık pozisyonlar history içine taşınır.</span>' +
            '</button>' +
          '</div>' +

          '<div class="modal-actions">' +
            HMTSTC_UI.btn(
              "Vazgeç",
              "btn-ghost",
              "onclick=\"HMTSTC_APP.set({modal:false})\""
            ) +
          '</div>' +
        '</div>' +
      '</div>'
    );
  },

  renderResetModal: function () {
    if (!HMTSTC_APP.state.resetModal) {
      return "";
    }

    return (
      '<div class="modal">' +
        '<div class="modal-box reset-modal-box">' +
          '<h2>Bot Verilerini Sıfırla</h2>' +
          '<p>Bu işlem aşağıdaki verileri kalıcı olarak sıfırlar:</p>' +

          '<div class="reset-warning-list">' +
            '<div>Açık pozisyonlar</div>' +
            '<div>İşlem geçmişi</div>' +
            '<div>Log kayıtları</div>' +
            '<div>Performans geçmişi</div>' +
            '<div>Bot başlama zamanı ve tick bilgisi</div>' +
          '</div>' +

          '<p class="reset-danger-text">Bu işlem geri alınamaz. Ayarlar korunur.</p>' +

          '<div class="modal-actions">' +
            HMTSTC_UI.btn(
              "Vazgeç",
              "btn-ghost",
              "onclick=\"HMTSTC_APP.set({resetModal:false})\""
            ) +

            HMTSTC_UI.btn(
              "Evet, Sıfırla",
              "btn-danger",
              "onclick=\"HMTSTC_APP.confirmResetBotData()\""
            ) +
          '</div>' +
        '</div>' +
      '</div>'
    );
  },

  renderCriticalModalStandard: function () {
    return this.renderConfirmModal();
  },

  renderConfirmModal: function () {
    const modal = HMTSTC_APP.state.confirmModal;

    if (!modal) {
      return "";
    }

    const level = modal.level || "warn";

    return '<div class="modal confirm-modal ux-critical-modal-standard" data-modal-level="' + level + '">' +
      '<div class="modal-box confirm-modal-box ' + level + '">' +
        '<h2>' + HMTSTC_APP.escapeHtml(modal.title || "İşlem Onayı") + '</h2>' +
        '<p>' + HMTSTC_APP.escapeHtml(modal.message || "") + '</p>' +
        '<div class="ux-modal-policy">' +
          '<b>Standard</b>' +
          '<span>Reason, risk summary and explicit confirmation are required for critical actions.</span>' +
        '</div>' +
        '<div class="modal-actions">' +
          '<button class="btn btn-ghost" onclick="HMTSTC_APP.state.confirmModal.onCancel()">' +
            HMTSTC_APP.escapeHtml(modal.cancelText || "Vazgeç") +
          '</button>' +
          '<button class="btn ' + (level === "critical" ? "btn-danger" : "btn-main") + '" onclick="HMTSTC_APP.state.confirmModal.onConfirm()">' +
            HMTSTC_APP.escapeHtml(modal.confirmText || "Onayla") +
          '</button>' +
        '</div>' +
      '</div>' +
    '</div>';
  },

  renderHeaderBotControls: function () {
    const bot = HMTSTC_DATA.botStatus || {};
    const settings = HMTSTC_DATA.settings || {};
    const botSettings = settings.bot || {};

    const running = Boolean(bot.bot_running);
    const controlMode = String(botSettings.control_mode || bot.control_mode || "").toLowerCase();
    const isAutomatic = controlMode === "automatic" || controlMode === "auto" || controlMode === "otomatik";

    return '<div class="header-bot-controls">' +
      '<button type="button" class="' + (running && !isAutomatic ? "active" : "") + '" onclick="HMTSTC_DASHBOARD_JARVIS.activateOpenMode()">Bot Başlat</button>' +
      '<button type="button" class="' + (!running ? "active" : "") + '" onclick="HMTSTC_DASHBOARD_JARVIS.activateClosedMode()">Bot Durdur</button>' +
      '<button type="button" class="' + (running && isAutomatic ? "active" : "") + '" onclick="HMTSTC_DASHBOARD_JARVIS.activateAutomaticMode()">Otomatik</button>' +
      '<button type="button" class="danger" onclick="HMTSTC_APP.set({modal:true})">Acil Durdur</button>' +
    '</div>';
  },

  renderTopMenu: function () {
    const state = HMTSTC_APP.state;
    const menu = (HMTSTC_DATA.menu || []).filter(function (item) {
      return HMTSTC_APP.hasPageAccess(item[0]);
    });

    function pageTitle() {
      const active = menu.find(function (item) {
        return item[0] === state.page;
      }) || menu[0] || ["dashboard", "Dashboard"];

      return HMTSTC_APP.escapeHtml(active[1] || "Dashboard");
    }

    const groups = [];

    menu.forEach(function (item) {
      const group = item[3] || "Genel";

      if (groups.indexOf(group) === -1) {
        groups.push(group);
      }
    });

    const headerMenu = groups.map(function (group) {
      const items = menu.filter(function (item) {
        return (item[3] || "Genel") === group;
      });

      return '<div class="header-menu-group">' +
        '<span>' + HMTSTC_APP.escapeHtml(group) + '</span>' +
        '<div>' +
          items.map(function (item) {
            return '<button type="button" class="' + (state.page === item[0] ? "active" : "") + '" onclick="HMTSTC_APP.set({page:\'' + item[0] + '\'})">' +
              HMTSTC_APP.escapeHtml(item[1]) +
            '</button>';
          }).join("") +
        '</div>' +
      '</div>';
    }).join("");

    const buildLabel = String(window.HMTSTC_BUILD_LABEL || "local").trim();
    const headerBotControls = "";

    return (
      '<header class="app-header award-header">' +
        '<div class="header-primary">' +
          '<div class="top-brand premium-brand">' +
            '<span class="brand-orbit"><i></i></span>' +
            '<div><b>HMTSTC</b><em>Güvenli işlem kontrol merkezi</em></div>' +
          '</div>' +

          '<div class="header-status-stack">' +
            headerBotControls +
          '</div>' +

          '<div class="user-bar premium-user-bar">' +
            '<span class="build-pill commit-marker-pill" title="Canlı deploy commit etiketi">COMMIT: ' + HMTSTC_APP.escapeHtml(buildLabel) + '</span>' +
            '<span class="role-pill">' + HMTSTC_APP.escapeHtml(state.role || "user") + '</span>' +
            '<span class="user-name">' + HMTSTC_APP.escapeHtml(state.user || "default") + '</span>' +
            '<button class="btn btn-ghost btn-small" onclick="HMTSTC_APP.logout()">Çıkış</button>' +
          '</div>' +
        '</div>' +

        '<div class="header-nav-row product-header-menu">' +
          '<div class="header-active-page"><span>Aktif sayfa</span><b>' + pageTitle() + '</b></div>' +
          '<nav class="header-page-menu" aria-label="Ana menü">' + headerMenu + '</nav>' +
        '</div>' +
      '</header>'
    );
  },

  renderSidebar: function () {
    const state = HMTSTC_APP.state;
    const menu = (HMTSTC_DATA.menu || []).filter(function (item) {
      return HMTSTC_APP.hasPageAccess(item[0]);
    });

    const groups = [];

    menu.forEach(function (item) {
      const group = item[3] || "Genel";

      if (groups.indexOf(group) === -1) {
        groups.push(group);
      }
    });

    return '<aside class="product-sidebar">' +
      '<div class="sidebar-title"><b>Menü</b><span>Ürün akışı</span></div>' +
      groups.map(function (group) {
        const items = menu.filter(function (item) {
          return (item[3] || "Genel") === group;
        });

        return '<div class="sidebar-group">' +
          '<span>' + HMTSTC_APP.escapeHtml(group) + '</span>' +
          items.map(function (item) {
            return '<button class="' + (state.page === item[0] ? "active" : "") + '" onclick="HMTSTC_APP.set({page:\'' + item[0] + '\'})">' +
              HMTSTC_APP.escapeHtml(item[1]) +
            '</button>';
          }).join("") +
        '</div>';
      }).join("") +
    '</aside>';
  },

  renderMobileMenu: function () {
    const state = HMTSTC_APP.state;
    const menu = (HMTSTC_DATA.menu || []).filter(function (item) {
      return HMTSTC_APP.hasPageAccess(item[0]);
    });

    return (
      '<div class="mobile-select">' +
        '<select onchange="HMTSTC_APP.set({page:this.value})">' +
          menu.map(function (item) {
            return (
              '<option value="' + HMTSTC_APP.escapeHtml(item[0]) + '" ' +
                (state.page === item[0] ? "selected" : "") +
              '>' +
                HMTSTC_APP.escapeHtml(item[1]) +
              '</option>'
            );
          }).join("") +
        '</select>' +
      '</div>'
    );
  },

  render: function () {
    const root = document.getElementById("root");

    if (!root) {
      return;
    }

    if (!HMTSTC_APP.state.auth) {
      root.innerHTML = HMTSTC_APP.renderLogin();
      return;
    }

    if (HMTSTC_APP.state.forcePasswordChange) {
      root.innerHTML = HMTSTC_APP.renderPasswordChange();
      return;
    }

    root.innerHTML =
      '<div class="app app-top-layout shell-app">' +
        '<main class="main main-full shell-main">' +
          this.renderTopMenu() +
          this.renderMobileMenu() +
          '<div class="product-workspace">' +
            '<section class="page dashboard-fit shell-page product-page-host">' +
              HMTSTC_APP.page() +
            '</section>' +
          '</div>' +
        '</main>' +
      '</div>' +
      HMTSTC_APP.renderModal() +
      HMTSTC_APP.renderResetModal() +
      HMTSTC_APP.renderConfirmModal();
  }
};
