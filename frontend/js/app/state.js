const HMTSTC_INITIAL_PAGE = (function () {
  try {
    const requested = new URLSearchParams(window.location.search).get("page");
    if (!requested || !/^[a-zA-Z0-9_-]+$/.test(requested)) return "dashboard";

    const role = String(localStorage.getItem("hmtstc_role") || "user").toLowerCase();
    const isAhmetOwner = String(localStorage.getItem("hmtstc_user") || "").toLowerCase() === "ahmet";
    const menu = (window.HMTSTC_DATA && window.HMTSTC_DATA.menu) || [];
    const item = menu.find(function (entry) { return entry[0] === requested; });

    if (!item) return "dashboard";

    const requiredRole = String(item[2] || "").toLowerCase();
    if (!requiredRole) return requested;
    if (requiredRole === "owner") return (isAhmetOwner || role === "owner") ? requested : "dashboard";
    if (requiredRole === "admin") return (isAhmetOwner || role === "owner") ? requested : "dashboard";
    if (requiredRole === "user") return requested;

    return "dashboard";
  } catch (error) {
    return "dashboard";
  }
}());

window.HMTSTC_APP_STATE = {
  auth: false,
  authRestorePending: Boolean(localStorage.getItem("hmtstc_token")),
  authRestoreChecked: false,
  authRestoreError: "",
  authDiagnostics: {
    tokenExists: Boolean(localStorage.getItem("hmtstc_token")),
    authMeStatus: null,
    lastRestoreAt: null,
    lastBlockReason: ""
  },
  user: localStorage.getItem("hmtstc_user") || "default",
  role: localStorage.getItem("hmtstc_role") || "user",
  forcePasswordChange: localStorage.getItem("hmtstc_force_password_change") === "true",
  token: localStorage.getItem("hmtstc_token") || null,
  loginError: "",

  page: HMTSTC_INITIAL_PAGE,
  mode: "live",
  pnl: 0,

  modal: false,
  resetModal: false,

  logLevel: "all",
  logEvent: "all",
  query: "",

  apiReady: false,
  apiSyncReady: false,
  syncInProgress: false,
  lastSyncAt: null,
  settingsLoaded: false,

  coinFilterDraft: null,
  coinFilterDirty: false,
  coinFilterDraftSource: "",
  coinFilterLastSavedAt: null,
  coinFilterLastSavedSnapshot: null,
  coinFilterPersistedCoinFilter: null,
  coinFilterPersistedAt: null,
  coinFilterBundleOverwriteGuarded: false,
  coinFilterSaveProof: null,
  coinFilterSaving: false,
  coinFilterSaveStatus: "idle",
  coinFilterSaveMessage: "",
  coinFilterTestScanRunning: false,
  coinFilterScanLoading: false,

  strategyDirty: false,
  strategySaving: false,

  performanceStart: null,
  performanceEnd: null,

  agentThinking: false,
  agentMessageDraft: "",
  agentLastError: "",
  agentVoiceListening: false,
  agentVoiceSpeaking: false,
  agentAutoSpeak: true,
  agentConversationMode: false,

  usersDraft: null,
  usersMessage: "",
  usersLoaded: false,
  usersLoading: false,

  ruleEditorTab: "filter",
  ruleEditorDirty: false,
  ruleEditorMode: "new",
  ruleEditorActiveId: "",
  ruleEditorMessage: "",
  lastKnownRulesSelection: {
    filter: null,
    strategy: null
  },
  dashboardRenderedRuleSelection: null,
  rulesSelectionProof: null,
  rulesSelectionProofHistory: [],
  paperLabEngineStatus: "idle",
  paperLabRunning: false,
  paperLabRunId: "",
  paperLabCandidateCount: 0,
  paperLabModelCount: 0,
  paperLabAccepted: 0,
  paperLabRejected: 0,
  paperLabStartedAt: null,
  paperLabCompletedAt: null,
  paperLabRun: null,
  lastPaperLabResult: null,
  paperLabStatusLastFetchMs: 0,
  paperLabStatusFetchInProgress: false,
  paperLabStatusMinIntervalMs: 60000,
  paperLabStatusLoading: false,

  botCommandPending: "",
  botCommandPendingSince: 0,

  marketQuery: "",
  marketView: "all",
  marketSort: "volume",
  coinFilterQuery: "",
  coinFilterStatus: "all",

  auditQuery: "",
  auditResult: "all",
  backupMessage: "",
  intelligenceTab: "overview"
};

window.HMTSTC_APP = window.HMTSTC_APP || {
  state: window.HMTSTC_APP_STATE
};
