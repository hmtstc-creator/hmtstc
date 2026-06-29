# Active / Legacy File Map

## 1. Active Files

| File | Status | Reason | Next action | Can edit in Package 2 |
| --- | --- | --- | --- | --- |
| `frontend/index.html` | ACTIVE | Defines CSS/JS load chain | Keep as frontend entrypoint | Yes, controlled |
| `frontend/css/styles.css` | ACTIVE | Loaded by index | UI styling baseline | Yes, controlled |
| `frontend/css/dashboard-funnel.css` | ACTIVE | Loaded by index | Dashboard funnel styling | Yes, controlled |
| `frontend/js/config.js` | ACTIVE | Loaded before data; sets API base | Review env coupling | Yes, controlled |
| `frontend/js/data.js` | ACTIVE | Initializes `HMTSTC_DATA` and menu | Keep as data bootstrap | Yes |
| `frontend/js/ui.js` | ACTIVE | Loaded helper layer | Keep helper baseline | Yes |
| `frontend/js/pages/base.js` | ACTIVE | Page registry base | Keep | Yes |
| `frontend/js/pages/settings.js` | ACTIVE | Settings page render source | Keep | Yes |
| `frontend/js/pages/coinFilter.js` | ACTIVE | Coin Filter page render source | Keep | Yes |
| `frontend/js/pages/ruleEditor.js` | ACTIVE | Rule editor page render source | Keep | Yes |
| `frontend/js/pages/users.js` | ACTIVE | Users page render source | Keep | Yes |
| `frontend/js/pages/strategies.js` | ACTIVE | Strategies page render source | Keep | Yes |
| `frontend/js/pages/dashboard.js` | ACTIVE | Dashboard page render source | Keep | Yes |
| `frontend/js/pages/admin.js` | ACTIVE | Admin page render source | Keep | Yes |
| `frontend/js/app/state.js` | ACTIVE | App state bootstrap | Keep | Yes |
| `frontend/js/app/api.js` | ACTIVE | API sync/fetch layer | Keep; contract critical | Yes, careful |
| `frontend/js/app/auth.js` | ACTIVE | Login/logout/password flow | Keep; auth critical | Yes, careful |
| `frontend/js/app/settings.js` | ACTIVE | Settings actions | Keep | Yes |
| `frontend/js/app/bot.js` | ACTIVE | Bot actions | Keep; trading-adjacent | Yes, careful |
| `frontend/js/app/agent.js` | ACTIVE | Agent/chat/report actions | Keep | Yes |
| `frontend/js/app/rules.js` | ACTIVE | Rule CRUD/action layer | Keep | Yes, careful |
| `frontend/js/app/users.js` | ACTIVE | User/API connection actions | Keep; secret-adjacent | Yes, careful |
| `frontend/js/app/audit.js` | ACTIVE | Audit actions | Keep | Yes |
| `frontend/js/app/realApproval.js` | ACTIVE | Real approval/report actions | Keep; live-trade adjacent | Yes, high caution |
| `frontend/js/app/realTrade.js` | ACTIVE | Real trade UI action layer | Keep; live-trade critical | Yes, dedicated package only |
| `frontend/js/app/intelligence.js` | ACTIVE | Intelligence action helper | Keep | Yes |
| `frontend/js/app/render.js` | ACTIVE | Render coordinator | Keep | Yes |
| `frontend/js/app.js` | ACTIVE | Merges app modules | Keep | Yes |
| `frontend/js/app/init.js` | ACTIVE | Final app init | Keep last | Yes |
| `backend/main.py` | ACTIVE | FastAPI composition root and scheduler startup | Keep; endpoint root | Yes, careful |
| `backend/core/auth.py` | ACTIVE | Auth and role gates | Keep | Yes, auth package only |
| `backend/core/storage.py` | ACTIVE | Runtime JSON load/save | Keep | Yes, storage package only |
| `backend/routes/*.py` | ACTIVE | API route surface | Keep | Yes, route-specific |
| `backend/services/*.py` | ACTIVE | Domain/service implementation | Keep | Yes, service-specific |
| `deploy/nginx.conf` | DEPLOY_ACTIVE | Production reverse proxy | Do not change in Package 2 unless deploy package | No by default |
| `deploy/hmtstc-backend.service` | DEPLOY_ACTIVE | Backend systemd service | Do not change in Package 2 unless deploy package | No by default |
| `deploy/deploy.sh` | DEPLOY_ACTIVE | Production deploy automation | Do not change in Package 2 unless deploy package | No by default |
| `webhook_server.py` | DEPLOY_ACTIVE | Webhook deploy trigger | Do not change in Package 2 unless deploy package | No by default |

## 2. Legacy Candidates

| File | Status | Reason | Next action | Can edit in Package 2 |
| --- | --- | --- | --- | --- |
| `frontend/js/pages.js` | NOT_PRESENT | Package prompt referenced it, but local repo does not have it | No deletion needed | No |
| `frontend/js/pages/backups.js` | LEGACY_CANDIDATE/STUB | Exists but is not loaded and file size is 2 bytes | Decide remove/load/ignore in Package 2 | Yes |
| `frontend/js/app/backups.js` | LEGACY_CANDIDATE/STUB | Exists but is not loaded and file size is 3 bytes | Decide remove/load/ignore in Package 2 | Yes |
| `Paketler/` | LOCAL_UNTRACKED_CONTEXT | Contains package instruction files, not tracked in git status | Keep separate from source diff | No by default |
| `ahmet.md` | UNKNOWN | Root markdown outside prompt scope | Review ownership before editing | No by default |
| `todo.md` | ACTIVE_DOC_OR_UNKNOWN | Root todo document, not part of Package 1 output | Use as context only | Yes, if requested |

## 3. Runtime Stores

| File | Status | Reason | Next action | Can edit in Package 2 |
| --- | --- | --- | --- | --- |
| `backend/shadow_store.json` | RUNTIME_STORE_IGNORED | Exists locally, ignored, contains user runtime/audit data | Do not edit manually | No |
| `backend/settings_store.json` | RUNTIME_STORE_ABSENT | Ignored by policy but not present locally | Confirm deploy example policy | No |
| `backend/auth_store.json` | RUNTIME_STORE_ABSENT | Ignored by policy | Runtime only | No |
| `backend/rule_store.json` | RUNTIME_STORE_ABSENT | Ignored by policy | Runtime only | No |
| `backend/audit_store.json` | RUNTIME_STORE_ABSENT | Ignored by policy | Runtime only | No |
| `backend/real_trade_store.json` | RUNTIME_STORE_ABSENT | Ignored by policy | Runtime only | No |
| `backend/binance_credentials_store.json` | RUNTIME_STORE_IGNORED_AFTER_PACKAGE_2 | Credential-shaped runtime file must not be tracked by git | Keep local only; use `backend/binance_credentials_store.example.json` as sanitized repo template | No, runtime only |
| `backend/binance_credentials_store.example.json` | EXAMPLE_STORE_TRACKED | Sanitized placeholder template | Keep tracked | Yes, example-only |
| `backend/settings_store.example.json` | EXAMPLE_STORE_TRACKED | `deploy/deploy.sh` expects example source for runtime initialization | Keep tracked | Yes, example-only |
| `backend/shadow_store.example.json` | EXAMPLE_STORE_TRACKED | `deploy/deploy.sh` expects example source for runtime initialization | Keep tracked | Yes, example-only |

## 4. Deploy Files

| File | Status | Reason | Next action | Can edit in Package 2 |
| --- | --- | --- | --- | --- |
| `deploy/nginx.conf` | DEPLOY | Controls frontend root and `/api` proxy | Leave unchanged | No |
| `deploy/hmtstc-backend.service` | DEPLOY | Controls Uvicorn host/port/user/env | Leave unchanged | No |
| `deploy/deploy.sh` | DEPLOY | Installs deps, sets permissions, restarts services | Leave unchanged | No |
| `webhook_server.py` | DEPLOY | Verifies GitHub webhook and triggers deploy | Leave unchanged | No |

## 5. Unknown Files

| File | Status | Reason | Next action | Can edit in Package 2 |
| --- | --- | --- | --- | --- |
| `.codex/` | LOCAL_TOOLING | Local Codex metadata | Ignore for product work | No |
| `Paketler/paket1.md` | LOCAL_UNTRACKED_CONTEXT | User instruction source | Do not include in product diff | No |
| `Paketler/paket2.md` | LOCAL_UNTRACKED_CONTEXT | Next package source | Read only when Paket 2 starts | No |

## 6. Package 2 Decision Notes

Package 2 should not assume the repo is an early mock-only system. It should begin from these facts:

- Active frontend is modular and loaded through `frontend/index.html`.
- There is no active or inactive `frontend/js/pages.js` file locally.
- Auth, user roles, Binance, Futures, real-trade, production and quality routes already exist.
- `backend/binance_credentials_store.json` is now runtime-only by Package 2 policy and must stay ignored.
- Deploy script store example expectations are satisfied by sanitized example files.
- Runtime stores must remain runtime-only.
