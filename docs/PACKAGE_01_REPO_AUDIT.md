# PACKAGE 01 - Repo Audit

## 1. Git Durumu

- Current branch: `main`
- Working tree before Package 1 docs: `?? Paketler/`
- Latest commits:
  - `b071937 Rev4010`
  - `dc14b7f Rev4011`
  - `e0681cd Rev4011`
  - `9ea3e65 Rev4011`
  - `0be545f Rev4011`

Not: `Paketler/` bu paketten once zaten untracked durumdaydi. Paket 1 kapsaminda kod, frontend, backend, deploy veya runtime store dosyasi degistirilmedi.

## 2. Repo Dosya Agaci

Root files and directories:

```text
.codex/
.git/
backend/
deploy/
frontend/
Paketler/
scripts/
.gitignore
ahmet.md
README.md
todo.md
webhook_server.py
```

Main tracked source files outside the very large `backend/services/` and `scripts/` trees:

```text
backend/.env.example
backend/binance_credentials_store.json
backend/main.py
backend/requirements.txt
backend/contracts/*.py
backend/core/*.py
backend/infrastructure/**/*.py
backend/routes/*.py
deploy/deploy.sh
deploy/hmtstc-backend.service
deploy/nginx.conf
frontend/assets/jarvis-background.jpg
frontend/css/dashboard-funnel.css
frontend/css/styles.css
frontend/index.html
frontend/js/app/*.js
frontend/js/pages/*.js
frontend/js/app.js
frontend/js/config.example.js
frontend/js/config.js
frontend/js/data.js
frontend/js/ui.js
```

Unknown/extra Package 1 observation:

- `docs/` did not exist before this package.
- `Paketler/` exists locally and is untracked.
- `backend/services/` and `scripts/` are much larger than the original package prompt baseline and contain many revision/quality/live-readiness services.

## 3. Frontend Yukleme Zinciri

`frontend/index.html` active load chain:

1. `frontend/css/styles.css` - ACTIVE
2. `frontend/css/dashboard-funnel.css` - ACTIVE
3. `frontend/js/config.js` - ACTIVE
4. `frontend/js/data.js` - ACTIVE
5. `frontend/js/ui.js` - ACTIVE
6. `frontend/js/pages/base.js` - ACTIVE
7. `frontend/js/pages/settings.js` - ACTIVE
8. `frontend/js/pages/coinFilter.js` - ACTIVE
9. `frontend/js/pages/ruleEditor.js` - ACTIVE
10. `frontend/js/pages/users.js` - ACTIVE
11. `frontend/js/pages/strategies.js` - ACTIVE
12. `frontend/js/pages/dashboard.js` - ACTIVE
13. `frontend/js/pages/admin.js` - ACTIVE
14. `frontend/js/app/state.js` - ACTIVE
15. `frontend/js/app/api.js` - ACTIVE
16. `frontend/js/app/auth.js` - ACTIVE
17. `frontend/js/app/settings.js` - ACTIVE
18. `frontend/js/app/bot.js` - ACTIVE
19. `frontend/js/app/agent.js` - ACTIVE
20. `frontend/js/app/rules.js` - ACTIVE
21. `frontend/js/app/users.js` - ACTIVE
22. `frontend/js/app/audit.js` - ACTIVE
23. `frontend/js/app/realApproval.js` - ACTIVE
24. `frontend/js/app/realTrade.js` - ACTIVE
25. `frontend/js/app/intelligence.js` - ACTIVE
26. `frontend/js/app/render.js` - ACTIVE
27. `frontend/js/app.js` - ACTIVE
28. `frontend/js/app/init.js` - ACTIVE, app init loads last

Special check:

- `frontend/js/pages.js` does not exist in the local repo.
- `frontend/js/pages/backups.js` and `frontend/js/app/backups.js` exist but are 2-3 byte stubs and are not loaded by `index.html`; status: `LEGACY_CANDIDATE` / `STUB`.
- The actual active frontend is modular and broader than the package prompt's older expected list.

## 4. Frontend Sayfa Haritasi

| Page | File | Active source | Reads data from | Calls backend API | Save/action risk |
| --- | --- | --- | --- | --- | --- |
| Dashboard | `frontend/js/pages/dashboard.js` | Yes | `HMTSTC_DATA.dashboard`, positions, settings, real summaries | Uses app sync and direct settings save path | Real-trade state is displayed; no code change in this package |
| Settings | `frontend/js/pages/settings.js`, `frontend/js/app/settings.js` | Yes | `HMTSTC_DATA.settings` | `/api/settings`, `/api/settings/*` | Saves settings and strategy/coin filter changes |
| Coin Filter | `frontend/js/pages/coinFilter.js` | Yes | settings coin filter and local draft | `/api/settings` | Saves filter config |
| Rule Editor | `frontend/js/pages/ruleEditor.js`, `frontend/js/app/rules.js` | Yes | `HMTSTC_DATA.rules`, examples | `/api/rules/*` | Creates, deletes, validates and activates rules |
| Strategies | `frontend/js/pages/strategies.js` | Yes | reports, strategies, intelligence data | `/api/models/*`, `/api/settings/strategies` | Strategy changes and reports |
| Users | `frontend/js/pages/users.js`, `frontend/js/app/users.js` | Yes | `HMTSTC_DATA.usersPayload`, auth/localStorage | `/api/users/*` | User creation, password reset, API connection save/delete |
| Admin | `frontend/js/pages/admin.js` | Yes | production/readiness/audit summaries | API data hydrated by app sync | High-risk operational view, mostly reporting |

Core app data flow:

- `frontend/js/config.js` sets `apiBase` to `http://127.0.0.1:8000` locally and `http://178.105.40.99` in production.
- `frontend/js/data.js` initializes `HMTSTC_DATA` and menu.
- `frontend/js/app/api.js` handles bearer token headers, `/api/dashboard/bundle` sync, fallback individual sync, heavy sync, and unauthorized cleanup.
- `frontend/js/app/auth.js` handles login/logout/change password and stores token/user/role in `localStorage`.

## 5. Backend Endpoint Haritasi

`backend/main.py` creates the FastAPI app, configures CORS, starts the runtime scheduler unless test flags are set, and includes these routers:

```text
auth_router
agent_router
binance_router
bot_router
dashboard_router
settings_router
model_router
rule_router
users_router
audit_router
intelligence_router
quality_router
real_router
observability_router
summary_router
production_router
```

App-level endpoints:

| Endpoint | Method | Function | Auth | Store use | Live trading risk |
| --- | --- | --- | --- | --- | --- |
| `/` | GET | `root` | No | No | Low |
| `/health` | GET | `health` | No | No | Low |
| `/health/ops` | GET | `operational_health` | No | Reads shadow/settings and deploy safety | Medium, exposes operational status but not secrets |

Route file summary:

| Route file | Prefix | Route count | Auth shape |
| --- | --- | ---: | --- |
| `agent_routes.py` | `/api/agent` | 10 | user |
| `audit_routes.py` | `/api/audit` | 12 | user/owner |
| `auth_routes.py` | `/api/auth` | 5 | login public, other user/owner |
| `binance_futures_routes.py` | `/api/futures` | 56 | user/owner |
| `binance_routes.py` | `/api/binance` | 8 | user/owner |
| `bot_routes.py` | `/api/bot` | 17 | user/owner |
| `dashboard_routes.py` | `/api` | 7 | user |
| `intelligence_routes.py` | `/api/intelligence` | 294 | mostly user, some owner |
| `karabasan_routes.py` | `/api/karabasan` | 19 | user |
| `model_routes.py` | `/api/models` | 40 | user/owner |
| `observability_routes.py` | `/api/observability` | 9 | user |
| `production_routes.py` | `/api/production` | 107 | user/owner |
| `quality_routes.py` | `/api/quality` | 265 | user |
| `real_routes.py` | `/api/real` | 47 | mostly owner |
| `rule_routes.py` | `/api/rules` | 30 | user/admin via rule helpers |
| `settings_routes.py` | `/api/settings` | 21 | user |
| `summary_routes.py` | `/api` | 1 | user |
| `users_routes.py` | `/api/users` | 11 | user/owner |

Important active frontend-facing endpoints include:

```text
POST /api/auth/login
GET /api/auth/me
POST /api/auth/logout
POST /api/auth/change-password
GET /api/dashboard/bundle
GET /api/dashboard
GET /api/positions
GET /api/history
GET /api/logs
GET/POST /api/settings
GET/POST /api/settings/coin-filter
GET/POST /api/settings/strategies
GET /api/bot/status
POST /api/bot/start
POST /api/bot/stop
POST /api/bot/emergency-stop
GET/POST/DELETE /api/audit
GET/POST/DELETE /api/users...
GET/POST/DELETE /api/rules...
GET /api/binance/market
GET /api/intelligence/overview
GET/POST /api/real...
```

Backend decision:

- The repo is no longer a minimal mock-only backend. It includes auth, user isolation helpers, Binance-facing modules, real trade gates and many production/quality endpoints.
- Live trading remains guarded by explicit owner-level endpoints, deploy/startup lock behavior, and real-trade safety services. This package did not validate exchange behavior or place orders.

## 6. JSON Store ve Secret Riskleri

Observed store files:

| File | Exists locally | Git tracked | `.gitignore` rule | Risk |
| --- | --- | --- | --- | --- |
| `backend/shadow_store.json` | Yes | No | Ignored | Runtime store risk; contains user runtime/audit data |
| `backend/settings_store.json` | No | No | Ignored | Expected runtime store but absent locally |
| `backend/auth_store.json` | No | No | Ignored | Expected runtime store for auth |
| `backend/rule_store.json` | No | No | Ignored | Expected runtime store for rules |
| `backend/audit_store.json` | No | No | Ignored | Expected runtime store for audit |
| `backend/real_trade_store.json` | No | No | Ignored | Expected runtime store for real trade |
| `backend/binance_credentials_store.json` | Yes | Yes | No explicit ignore | `POSSIBLE_SECRET_FOUND_MASKED` / tracked credential-shaped store |

Masked sensitive finding:

```text
backend/binance_credentials_store.json
user: binance_mainnet_guard_user
api_key: demo***3456
api_secret: demo***3456
environment: mainnet
```

`backend/.env.example` contains placeholders only:

```text
HMTSTC_SECRET_KEY=replace***secret
HMTSTC_BINANCE_API_KEY=replace***only
HMTSTC_BINANCE_API_SECRET=replace***only
```

Package 1 decision tags:

- `POSSIBLE_SECRET_FOUND_MASKED`: `backend/binance_credentials_store.json` is tracked and contains credential-shaped fields.
- `JSON_STORE_RUNTIME_RISK`: runtime state is JSON-file based and includes local ignored store data.
- `GITIGNORE_MISSING_RULE`: `backend/binance_credentials_store.json` is not ignored.
- `NO_SECRET_FOUND`: not applicable globally because credential-shaped demo values were found.

## 7. Deploy Yapisi

`deploy/nginx.conf`:

- `server_name`: `178.105.40.99`
- frontend root: `/var/www/hmtstc/frontend`
- `/api/` proxy: `http://127.0.0.1:8000/api/`
- `/health` proxy: `http://127.0.0.1:8000/health`

`deploy/hmtstc-backend.service`:

- service name implied by file: `hmtstc-backend.service`
- user/group: `hmtstc:www-data`
- working directory: `/var/www/hmtstc/backend`
- env file: `/var/www/hmtstc/backend/.env`
- command: `uvicorn main:app --host 127.0.0.1 --port 8000`
- restart policy: `always`

`deploy/deploy.sh`:

- prepares `/var/www/hmtstc/backend/runtime_backups`
- runs `scripts/pre_deploy_backup.py`
- creates backend venv if missing
- runs `pip install -r requirements.txt`
- creates `settings_store.json` and `shadow_store.json` from examples if examples exist
- updates systemd service and Nginx site
- restarts backend, reloads Nginx, attempts webhook restart
- runs `scripts/post_deploy_check.py --offline`
- checks `/health` and `/health/ops`

`webhook_server.py`:

- exposes `POST /webhook` with GitHub HMAC signature verification using `WEBHOOK_SECRET`
- triggers `hmtstc-deploy.service`
- exposes `GET /webhook/health`
- logs to `/var/log/hmtstc-webhook.log`

## 8. Saglik Kontrolu Sonuclari

Static/read-only checks completed:

- `git status --short`: showed pre-existing `?? Paketler/`
- `git branch --show-current`: `main`
- `git log --oneline -5`: captured above
- `frontend/index.html` load chain: parsed
- backend route inventory: parsed
- JSON store and `.gitignore`: parsed
- deploy files: parsed

Runtime checks executed:

| Check | Result | Note |
| --- | --- | --- |
| `python --version` | Fail | `python` command not found on PATH |
| `py --version` | Pass | Python 3.14.4 |
| `py -m py_compile backend/main.py webhook_server.py` | Pass | Syntax compile completed |
| `py -c "... import main; print('backend import ok')"` | Partial | Printed `backend import ok`, then command hit timeout during process shutdown |
| Direct backend health function with scheduler disabled | Pass | Returned `{'status': 'healthy'}` |
| FastAPI `TestClient` health | Fail | `httpx` dependency missing from local Python environment |
| Local Uvicorn server + curl | Not run | Avoided long-running process for documentation-only Package 1 |
| Frontend local static server/browser | Not run | No frontend code changed; Package 1 is documentation-only |

Health conclusion:

- Backend syntax is valid under local `py`.
- Backend `/health` payload is healthy when called directly with runtime scheduler disabled.
- Full HTTP startup smoke should be rerun in a runtime package or deployment check with dependencies and long-running processes allowed.

## 9. Kritik Riskler

1. `backend/binance_credentials_store.json` is tracked and contains credential-shaped `api_key` / `api_secret` fields, even if demo-labeled.
2. Runtime data uses local JSON stores; production safety depends on file permissions, `.gitignore`, backup discipline and service ownership.
3. Backend surface is very large: 959 route decorators across `backend/routes/*.py`, including real-trade and production endpoints.
4. `frontend/js/config.js` hard-codes production API host `http://178.105.40.99`; this is not a secret but is an environment coupling.
5. `deploy/deploy.sh` references `settings_store.example.json` and `shadow_store.example.json`, but those files are not present in the current local `backend/` listing.
6. `frontend/js/pages/backups.js` and `frontend/js/app/backups.js` are unloaded stubs and should not be assumed active.

## 10. Paket 2'ye Gecis Karari

Paket 2'ye gecis: **No, conditional**.

Bloklayici/risk giderme onerileri:

1. `backend/binance_credentials_store.json` icin karar ver: runtime-only ignored store mu, sanitized example file mi?
2. Missing example store dosyalarini deploy beklentisiyle karsilastir: `settings_store.example.json` ve `shadow_store.example.json`.
3. API/route envanteri ile frontend aktif sayfa haritasini Paket 2'de tek kaynak dokumana indir.
4. Real-trade endpointleri icin owner gate, deploy lock ve dry-run/place ayrimini tekrar dogrula.

Paket 1 tamamlandi. Mevcut repo yapisi incelendi, aktif/legacy dosya ayrimi cikarildi, mock/canli ayrimi netlestirildi, backend/frontend/deploy baslangic mimarisi raporlandi. Kod dosyalarinda degisiklik yapilmadi. Paket 2'ye gecis icin riskler ve kapsam netlestirildi.
