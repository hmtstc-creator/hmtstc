window.HMTSTC_RUNTIME_CONFIG = window.HMTSTC_RUNTIME_CONFIG || {};
window.HMTSTC_API_BASE = window.HMTSTC_RUNTIME_CONFIG.apiBase || window.HMTSTC_API_BASE || "";
window.HMTSTC_BUILD_LABEL = window.HMTSTC_RUNTIME_CONFIG.buildLabel || localStorage.getItem("hmtstc_build_label") || "yükleniyor";

window.HMTSTC_DATA = {
  menu: [
    ["dashboard", "Dashboard", ["owner", "admin"], "Genel"],

    ["settings", "Ayarlar", null, "Ayar / Kural"],
    ["coinFilter", "Coin Filter", ["owner", "admin"], "Ayar / Kural"],
    ["ruleEditor", "Paper Lab / Kural Editörü", "ahmet", "Ayar / Kural"],
    ["strategies", "Stratejiler", ["owner", "admin"], "Ayar / Kural"],

    ["users", "Kullanıcılar", "owner", "Operasyon"],
    ["admin", "Admin", ["owner", "admin"], "Yönetim"]
  ],







  positions: [],
  history: [],

  logs: [],
  audit: { status: "idle", items: [] }
};

