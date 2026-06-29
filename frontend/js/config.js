window.HMTSTC_RUNTIME_CONFIG = window.HMTSTC_RUNTIME_CONFIG || (function () {
  const host = String((window.location && window.location.hostname) || "").toLowerCase();
  const isLocal = !host || host === "localhost" || host === "127.0.0.1" || host === "::1";
  return {
    apiBase: isLocal ? "http://127.0.0.1:8000" : "http://178.105.40.99",
    environment: isLocal ? "local" : "production"
  };
}());
