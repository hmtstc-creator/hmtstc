window.HMTSTC_APP = {
  state: window.HMTSTC_APP_STATE || {},

  set: function (changes) {
    Object.assign(this.state, changes);
    this.render();

    if (changes && changes.page === "strategies" && this.state.auth && !((window.HMTSTC_DATA || {}).reports || {}).status) {
      this.state.lastHeavySyncMs = 0;
      this.syncHeavyApiData();
    }
  },

  safeRenderAfterSync: function () {
    this.render();
  },

  isUserEditing: function () {
    const activeElement = document.activeElement;

    return !!(
      activeElement &&
      (
        activeElement.tagName === "INPUT" ||
        activeElement.tagName === "SELECT" ||
        activeElement.tagName === "TEXTAREA"
      )
    );
  }
};

Object.assign(
  window.HMTSTC_APP,
  window.HMTSTC_APP_API || {},
  window.HMTSTC_APP_AUTH || {},
  window.HMTSTC_APP_SETTINGS || {},
  window.HMTSTC_APP_BOT || {},
  window.HMTSTC_APP_AGENT || {},
  window.HMTSTC_APP_RULES || {},
  window.HMTSTC_APP_USERS || {},
  window.HMTSTC_APP_AUDIT || {},
  window.HMTSTC_APP_BACKUPS || {},
  window.HMTSTC_APP_REAL_APPROVAL || {},
  window.HMTSTC_APP_REAL_TRADE || {},
  window.HMTSTC_APP_INTELLIGENCE || {},
  window.HMTSTC_APP_RENDER || {}
);
