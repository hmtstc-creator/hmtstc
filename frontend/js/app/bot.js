window.HMTSTC_APP_BOT = {
  beginBotCommand: function (command) {
    if (HMTSTC_APP.state.botCommandPending) {
      this.pushOperationLine("Bot komutu zaten işleniyor.");
      return false;
    }
    HMTSTC_APP.state.botCommandPending = command;
    HMTSTC_APP.state.botCommandPendingSince = Date.now();
    HMTSTC_APP.render();
    window.setTimeout(function () {
      if (HMTSTC_APP.state.botCommandPending === command && Date.now() - HMTSTC_APP.state.botCommandPendingSince >= 5000) {
        HMTSTC_APP.state.botCommandPending = "";
        HMTSTC_APP.state.botCommandPendingSince = 0;
        HMTSTC_APP.render();
      }
    }, 5000);
    return true;
  },

  endBotCommand: function (command) {
    if (!command || HMTSTC_APP.state.botCommandPending === command) {
      HMTSTC_APP.state.botCommandPending = "";
      HMTSTC_APP.state.botCommandPendingSince = 0;
      HMTSTC_APP.render();
    }
  },

  checkFirstTickResult: function (attempt) {
    const app = this;
    const pollAttempt = Number(attempt || 0);
    window.setTimeout(async function () {
      try {
        const status = await HMTSTC_APP.fetchJson("/api/bot/status", {
          requestKind: "core_read",
          timeoutMs: 8000
        });
        HMTSTC_DATA.botStatus = Object.assign({}, HMTSTC_DATA.botStatus || {}, status || {});
        if ((status || {}).primary_runtime_problem === "first_tick_timeout") {
          app.pushOperationLine("Bot ilk taramada zaman aşımına düştü. CPU kilidi önlendi.");
        } else if ((status || {}).bot_running) {
          app.pushOperationLine("Backend status doğrulandı. Bot aktif.");
        } else if ((status || {}).requested_running && pollAttempt < 5) {
          app.pushOperationLine("Bot başlatıldı. İlk piyasa taraması hazırlanıyor.");
          app.checkFirstTickResult(pollAttempt + 1);
        }
      } catch (error) {
        console.warn("Bot start sonrası status geçici okunamadı; yeniden denenecek.", error);
        if (pollAttempt < 5) {
          app.checkFirstTickResult(pollAttempt + 1);
        }
      }
    }, 5000);
  },

  pushOperationLine: function (line) {
    const operation = HMTSTC_DATA.operation || { lines: [] };
    const lines = operation.lines || [];

    lines.push(new Date().toLocaleTimeString("tr-TR") + "  " + line);

    HMTSTC_DATA.operation = {
      message: line,
      lines: lines.slice(-2),
      updated_at: new Date().toLocaleTimeString("tr-TR")
    };

    HMTSTC_APP.render();
  },

  startBot: async function () {
    if (!HMTSTC_APP.state.auth) {
      this.pushOperationLine("BEKLE: Oturum açılmadan bot başlatılamaz.");
      return;
    }

    if (!HMTSTC_APP.state.apiReady && !HMTSTC_APP.state.apiSyncReady) {
      this.pushOperationLine("BEKLE: Backend API online doğrulanmadan bot başlatılamaz.");
      return;
    }

    if ((HMTSTC_DATA.botStatus || {}).requested_running) {
      this.pushOperationLine("Bot çalışma isteği zaten aktif.");
      return;
    }

    if (!this.beginBotCommand("start")) return;
    this.pushOperationLine("Bot açılıyor...");

    try {
      HMTSTC_DATA.botStatus = Object.assign({}, HMTSTC_DATA.botStatus || {}, {
        engine_status: "starting"
      });
      this.pushOperationLine("Canlı başlat komutu gönderiliyor...");

      const result = await HMTSTC_APP.fetchJson("/api/bot/start?mode=paper", {
        method: "POST",
        requestKind: "mutation",
        preventGlobalAbort: true,
        timeoutMs: 5000
      });

      if ((result || {}).ok === false) {
        HMTSTC_DATA.botStatus = Object.assign({}, HMTSTC_DATA.botStatus || {}, result || {});
        this.pushOperationLine("HATA: Bot loop başlatılamadı: " + ((result || {}).primary_runtime_problem || (result || {}).reason || "bilinmeyen hata"));
        return;
      }

      this.pushOperationLine("Bot açıldı. Durum doğrulanıyor.");

      let afterStatus = null;
      try {
        afterStatus = await HMTSTC_APP.fetchJson("/api/bot/status", {
          requestKind: "core_read",
          preventGlobalAbort: true,
          timeoutMs: 8000
        });
      } catch (statusError) {
        console.warn("Bot start sonrası status geçici okunamadı; yeniden denenecek.", statusError);
        HMTSTC_DATA.botStatus = Object.assign({}, HMTSTC_DATA.botStatus || {}, {
          requested_running: true,
          engine_status: "starting",
          bot_started_at: result.bot_started_at || null,
          mode: result.mode || "paper"
        });
        this.pushOperationLine("Bot durumu kontrol ediliyor...");
        this.checkFirstTickResult();
        return;
      }

      HMTSTC_DATA.botStatus = Object.assign({}, afterStatus || {}, {
        bot_started_at: (afterStatus || {}).bot_started_at || result.bot_started_at || null,
        mode: (afterStatus || {}).mode || result.mode || "paper"
      });

      if (!HMTSTC_DATA.botStatus.bot_running) {
        if (HMTSTC_DATA.botStatus.requested_running && ["starting", "restoring"].indexOf(HMTSTC_DATA.botStatus.engine_status) !== -1) {
          this.pushOperationLine("Bot başlatıldı. İlk piyasa taraması hazırlanıyor.");
          this.checkFirstTickResult();
        } else if (HMTSTC_DATA.botStatus.primary_runtime_problem === "first_tick_timeout") {
          this.pushOperationLine("Bot ilk taramada zaman aşımına düştü. CPU kilidi önlendi.");
        } else if (HMTSTC_DATA.botStatus.engine_status === "failed") {
          this.pushOperationLine("HATA: Bot güvenli şekilde durduruldu: " + (HMTSTC_DATA.botStatus.primary_runtime_problem || "bilinmeyen hata"));
        } else {
          this.pushOperationLine("HATA: Start isteği backend tarafından çalışma isteği olarak korunmadı.");
        }
        return;
      }

      this.pushOperationLine("Backend status doğrulandı. Bot aktif.");
      try {
        await HMTSTC_APP.auditAction("bot_start", "ok", "Bot başlatıldı ve status doğrulandı.", {});
      } catch (auditError) {
        this.pushOperationLine("UYARI: Bot start audit yazılamadı; bot çalışmaya devam ediyor.");
      }

      try {
        await HMTSTC_APP.syncApiData();
        this.pushOperationLine("Dashboard güncellendi. Canlı bot çalışıyor.");
      } catch (syncError) {
        console.warn("Bot start sonrası dashboard sync geçici başarısız:", syncError);
        this.pushOperationLine("Bot aktif. Dashboard verileri sonraki yenilemede güncellenecek.");
      }

    } catch (error) {
      console.error("Bot başlatma hatası:", error);
      HMTSTC_DATA.botStatus = Object.assign({}, HMTSTC_DATA.botStatus || {}, {
        engine_status: "error",
        last_error: HMTSTC_APP.apiErrorMessage(error, "Bot başlatılamadı.")
      });
      this.pushOperationLine("HATA: " + HMTSTC_APP.apiErrorMessage(error, "Bot başlatılamadı."));
      try {
        await HMTSTC_APP.auditAction("bot_start", "error", HMTSTC_APP.apiErrorMessage(error, "Bot başlatılamadı."), {});
      } catch (auditError) {
        this.pushOperationLine("UYARI: Bot start audit yazılamadı.");
      }
    } finally {
      this.endBotCommand("start");
    }
  },

  stopBot: async function () {
    if (!HMTSTC_APP.state.apiSyncReady) {
      this.pushOperationLine("BEKLE: Sistem doğrulanmadan bot durdurulamaz.");
      return;
    }

    if (!(HMTSTC_DATA.botStatus || {}).bot_running && !(HMTSTC_DATA.botStatus || {}).requested_running) {
      this.pushOperationLine("Bot zaten pasif.");
      return;
    }

    if (!this.beginBotCommand("stop")) return;
    this.pushOperationLine("Bot kapatılıyor...");

    try {
      const result = await HMTSTC_APP.fetchJson("/api/bot/stop", {
        method: "POST",
        requestKind: "mutation",
        preventGlobalAbort: true,
        timeoutMs: 5000
      });

      HMTSTC_DATA.botStatus = Object.assign({}, HMTSTC_DATA.botStatus || {}, {
        bot_running: false,
        requested_running: false,
        engine_status: "stopped",
        bot_stopped_at: result.bot_stopped_at || null,
        stop_reason: result.stop_reason || "user_requested_stop"
      });

      this.pushOperationLine("Bot kapalı.");
      await HMTSTC_APP.auditAction("bot_stop", "ok", "Bot durduruldu.", {});

      await HMTSTC_APP.syncApiData();

      this.pushOperationLine("Dashboard güncellendi. Bot kapalı.");

    } catch (error) {
      console.error("Bot durdurma hatası:", error);
      this.pushOperationLine("HATA: Bot durdurulamadı.");
      await HMTSTC_APP.auditAction("bot_stop", "error", HMTSTC_APP.apiErrorMessage(error, "Bot durdurulamadı."), {});
    } finally {
      this.endBotCommand("stop");
    }
  },

  emergencyStop: async function (action) {
    if (!HMTSTC_APP.state.apiSyncReady) {
      this.pushOperationLine("BEKLE: Sistem doğrulanmadan acil durdur uygulanamaz.");
      return;
    }

    if (!(HMTSTC_DATA.botStatus || {}).bot_running) {
      this.pushOperationLine("Bot zaten pasif.");
      return;
    }

    this.pushOperationLine("ACİL DURDUR komutu gönderiliyor...");

    try {
      HMTSTC_DATA.botStatus = Object.assign({}, HMTSTC_DATA.botStatus || {}, {
        bot_running: false,
        engine_status: "emergency_stopped"
      });

      HMTSTC_APP.set({ modal: false });

      const result = await HMTSTC_APP.fetchJson(
        "/api/bot/emergency-stop?action=" + encodeURIComponent(action),
        { method: "POST" }
      );

      HMTSTC_DATA.botStatus = Object.assign({}, HMTSTC_DATA.botStatus || {}, {
        bot_running: false,
        engine_status: "emergency_stopped",
        bot_stopped_at: result.bot_stopped_at || null,
        stop_reason: result.stop_reason || "emergency_stop"
      });

      this.pushOperationLine("Backend onayladı. Acil durdur tamamlandı.");
      await HMTSTC_APP.auditAction("emergency_stop", "ok", "Acil durdur tamamlandı.", { action: action });

      await HMTSTC_APP.syncApiData();

      this.pushOperationLine("Dashboard güncellendi. Bot kapalı.");

    } catch (error) {
      console.error("Acil durdurma hatası:", error);
      this.pushOperationLine("HATA: Acil durdur uygulanamadı.");
      await HMTSTC_APP.auditAction("emergency_stop", "error", HMTSTC_APP.apiErrorMessage(error, "Acil durdur uygulanamadı."), { action: action });
    }
  },

  resetBotData: function () {
    if (!HMTSTC_APP.state.apiSyncReady) {
      this.pushOperationLine("BEKLE: Sistem doğrulanmadan sıfırlama yapılamaz.");
      return;
    }

    HMTSTC_APP.set({ resetModal: true });
  },

  confirmResetBotData: async function () {
    if (!HMTSTC_APP.state.apiSyncReady) {
      this.pushOperationLine("BEKLE: Sistem doğrulanmadan sıfırlama yapılamaz.");
      return;
    }

    this.pushOperationLine("RESET komutu gönderiliyor...");

    try {
      HMTSTC_APP.set({ resetModal: false });

      await HMTSTC_APP.fetchJson("/api/bot/reset", {
        method: "POST"
      });

      HMTSTC_DATA.botStatus = {
        bot_running: false,
        engine_status: "reset",
        bot_started_at: null,
        bot_stopped_at: null,
        last_tick: null,
        last_updated_at: null,
        stop_reason: "reset"
      };

      HMTSTC_DATA.positions = [];
      HMTSTC_DATA.history = [];
      HMTSTC_DATA.logs = [];
      HMTSTC_DATA.performance = {
        status: "ok",
        count: 0,
        points: []
      };

      this.pushOperationLine("Bot verileri sıfırlandı.");
      await HMTSTC_APP.auditAction("bot_reset", "ok", "Bot verileri sıfırlandı.", {});

      await HMTSTC_APP.syncApiData();

      this.pushOperationLine("Dashboard sıfır durumla güncellendi.");

    } catch (error) {
      console.error("Bot sıfırlama hatası:", error);
      this.pushOperationLine("HATA: Bot verileri sıfırlanamadı.");
      await HMTSTC_APP.auditAction("bot_reset", "error", HMTSTC_APP.apiErrorMessage(error, "Bot verileri sıfırlanamadı."), {});
    }
  }
};
