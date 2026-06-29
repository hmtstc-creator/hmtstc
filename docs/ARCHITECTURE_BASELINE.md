# Architecture Baseline

## 1. Mevcut Calisan Mimari

Repo, statik frontend + FastAPI backend + Nginx reverse proxy + systemd servisleri seklinde calisacak bicimde kuruludur.

High-level flow:

```text
Browser
  -> frontend/index.html
  -> frontend/js/config.js determines API base
  -> frontend/js/app/api.js sends /api requests with Bearer token
  -> Nginx /api proxy
  -> FastAPI backend on 127.0.0.1:8000
  -> JSON runtime stores and service modules
```

Deploy flow:

```text
GitHub webhook
  -> webhook_server.py verifies HMAC
  -> starts hmtstc-deploy.service
  -> deploy/deploy.sh
  -> backend venv/dependencies/runtime permissions
  -> hmtstc-backend.service restart
  -> nginx reload
  -> post deploy smoke checks
```

## 2. Frontend Katmani

Active entrypoint:

- `frontend/index.html`

Active CSS:

- `frontend/css/styles.css`
- `frontend/css/dashboard-funnel.css`

Active config/data/UI:

- `frontend/js/config.js`
- `frontend/js/data.js`
- `frontend/js/ui.js`

Active pages:

- `frontend/js/pages/base.js`
- `frontend/js/pages/settings.js`
- `frontend/js/pages/coinFilter.js`
- `frontend/js/pages/ruleEditor.js`
- `frontend/js/pages/users.js`
- `frontend/js/pages/strategies.js`
- `frontend/js/pages/dashboard.js`
- `frontend/js/pages/admin.js`

Active app modules:

- `frontend/js/app/state.js`
- `frontend/js/app/api.js`
- `frontend/js/app/auth.js`
- `frontend/js/app/settings.js`
- `frontend/js/app/bot.js`
- `frontend/js/app/agent.js`
- `frontend/js/app/rules.js`
- `frontend/js/app/users.js`
- `frontend/js/app/audit.js`
- `frontend/js/app/realApproval.js`
- `frontend/js/app/realTrade.js`
- `frontend/js/app/intelligence.js`
- `frontend/js/app/render.js`
- `frontend/js/app.js`
- `frontend/js/app/init.js`

Frontend state assumptions:

- `HMTSTC_DATA` is global data state.
- `HMTSTC_APP.state` is initialized in `frontend/js/app/state.js`.
- Auth token, user and role are stored in `localStorage`.
- API base is local `http://127.0.0.1:8000` for local host and `http://178.105.40.99` otherwise.

## 3. Backend Katmani

Active backend entrypoint:

- `backend/main.py`

FastAPI app behavior:

- CORS allows production IP, GitHub Pages URL, and local dev origins.
- Lifespan starts a runtime scheduler unless testing flags disable it.
- Startup applies a real-trade lock policy through `apply_startup_real_trade_lock()`.
- Bot loop iterates users from shadow store and runs `run_bot_tick`.

Core backend directories:

- `backend/core/`: config, auth, storage and indicators.
- `backend/contracts/`: typed request contracts for settings, rules, real trade and common structures.
- `backend/routes/`: FastAPI route modules.
- `backend/services/`: large domain service layer with bot, Binance, real trade, production, quality and revision services.
- `backend/infrastructure/`: runtime scheduler and JSON repository wrapper.

Auth baseline:

- `backend/core/auth.py` provides `require_user`, `require_owner`, and `require_admin`.
- Most API routes require at least `require_user`.
- Owner-level operations appear in users, audit export/delete, real-trade actions, production and Binance control surfaces.

## 4. Data/Mock Katmani

Data is mixed:

- Some dashboard and service responses are built from local runtime JSON state.
- Some market/Binance modules can call Binance-oriented services.
- Real-trade modules expose preview, dry-run, place, lock/unlock and pilot endpoints.
- Quality and intelligence routes contain many generated/revision-style reports.

Runtime store paths and status:

| Store | Status |
| --- | --- |
| `backend/shadow_store.json` | Exists locally, ignored, runtime data |
| `backend/settings_store.json` | Not present locally, ignored by policy |
| `backend/auth_store.json` | Not present locally, ignored by policy |
| `backend/rule_store.json` | Not present locally, ignored by policy |
| `backend/audit_store.json` | Not present locally, ignored by policy |
| `backend/real_trade_store.json` | Not present locally, ignored by policy |
| `backend/binance_credentials_store.json` | Exists and is tracked; credential-shaped demo fields present |

Secret handling assumption:

- Runtime secrets must not be committed.
- Current `.gitignore` covers many runtime stores but not `backend/binance_credentials_store.json`.
- Reports must not print full secret values.

## 5. Deploy Katmani

Nginx:

- Serves frontend from `/var/www/hmtstc/frontend`.
- Proxies `/api/` to backend `/api/`.
- Proxies `/health` to backend `/health`.

Systemd backend:

- Runs as `hmtstc:www-data`.
- Uses `/var/www/hmtstc/backend/.env`.
- Starts Uvicorn at `127.0.0.1:8000`.

Deploy script:

- Prepares backups and permissions.
- Installs requirements.
- Manages runtime store initialization if example files exist.
- Restarts backend and reloads Nginx.
- Runs post-deploy smoke checks.

Webhook:

- Uses `WEBHOOK_SECRET` from `/var/www/hmtstc/backend/.env`.
- Starts `hmtstc-deploy.service`.

## 6. Hedef Mimariye Gore Farklar

The original package prompt described an early mock backend. The current local repo is beyond that point:

- Auth exists.
- User and owner roles exist.
- Binance and Binance Futures modules exist.
- Real-trade endpoints exist.
- Production readiness and quality routes exist.
- Frontend has user/admin/rule/real-trade app modules.

Remaining gaps/risk areas before live trading trust:

- Credential store tracking policy must be fixed.
- Runtime store examples referenced by deploy must be aligned with actual files.
- Real exchange behavior was not validated in this package.
- Route surface is large and needs a maintained API contract inventory.
- JSON runtime stores are operationally fragile without backup, locking and permission discipline.

## 7. Degistirilmemesi Gereken Varsayimlar

Until Package 2 explicitly changes them:

- `frontend/index.html` remains the source of the active script chain.
- `frontend/js/pages.js` should not be referenced as active; it does not exist locally.
- `frontend/js/pages/backups.js` and `frontend/js/app/backups.js` remain unloaded stubs.
- `backend/main.py` remains the backend composition root.
- Runtime JSON stores should not be manually edited for package work.
- `deploy/*` and `webhook_server.py` should be treated as production-sensitive.
- No live order path should be changed without a dedicated real-trade safety package.
