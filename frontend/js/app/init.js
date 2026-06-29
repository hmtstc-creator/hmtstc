window.HMTSTC_APP_INIT = {
  start: function () {
    if (HMTSTC_APP.restoreAuth) {
      HMTSTC_APP.restoreAuth().finally(function () {
        HMTSTC_APP.render();
      });
    }

    HMTSTC_APP.render();

    setInterval(function () {
      if (HMTSTC_APP.state.authRestorePending) {
        return;
      }

      if (!HMTSTC_APP.state.auth) {
        return;
      }

      if (HMTSTC_APP.isUserEditing()) {
        return;
      }

      if (HMTSTC_APP.state.syncInProgress) {
        return;
      }

      HMTSTC_APP.syncApiData({ skipHeavySync: false });
    }, 30000);
  }
};

HMTSTC_APP_INIT.start();
