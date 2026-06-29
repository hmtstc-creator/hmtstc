# Package 2 Readiness

## 1. Paket 2'ye Gecis Durumu

Paket 2'ye gecis durumu: **No, conditional**.

Reason:

- Paket 1 repo baseline is complete enough for planning.
- However, Package 2 should first address file hygiene and source-of-truth mismatches before feature work.

## 2. Bloklayici Riskler

1. `backend/binance_credentials_store.json` is tracked and contains masked credential-shaped fields:

```text
api_key: demo***3456
api_secret: demo***3456
environment: mainnet
```

2. `.gitignore` excludes many runtime stores but not `backend/binance_credentials_store.json`.
3. `deploy/deploy.sh` references `backend/settings_store.example.json` and `backend/shadow_store.example.json`, but those files were not present in the local `backend/` listing.
4. Backend API surface is broad: 959 route decorators across `backend/routes/*.py`; route contract drift risk is high.
5. Frontend and backend are no longer mock-only. Real-trade and Binance-facing modules exist and must not be edited casually.
6. Pre-existing untracked `Paketler/` means Package 1's ideal `git diff --name-only` expectation needs to account for user-local instruction files.

## 3. Onerilen Paket 2 Kapsami

Package 2 should focus on repository hygiene and contract clarity:

- Decide whether `backend/binance_credentials_store.json` becomes ignored runtime data or a sanitized `.example.json`.
- Align `.gitignore` with every runtime credential/state store.
- Add or remove deploy references to missing example store files.
- Create a concise API contract inventory from the current route modules.
- Confirm active frontend pages and remove/load/ignore stub backup modules.
- Update README/todo to reflect the current local architecture, not the older mock-only baseline.

## 4. Paket 2'de Dokunulacak Dosyalar

Recommended:

```text
.gitignore
README.md
todo.md
backend/binance_credentials_store.json or a sanitized replacement/example
deploy/deploy.sh only if store example policy is part of Package 2
docs/* if continuing documentation
```

Conditional:

```text
frontend/js/pages/backups.js
frontend/js/app/backups.js
backend/settings_store.example.json
backend/shadow_store.example.json
```

## 5. Paket 2'de Dokunulmayacak Dosyalar

Unless Package 2 is explicitly re-scoped, do not edit:

```text
backend/main.py
backend/routes/real_routes.py
backend/routes/binance_routes.py
backend/routes/binance_futures_routes.py
backend/services/real_*.py
backend/services/binance_*.py
backend/shadow_store.json
backend/settings_store.json
backend/auth_store.json
backend/rule_store.json
backend/audit_store.json
backend/real_trade_store.json
frontend/js/app/realTrade.js
frontend/js/app/realApproval.js
deploy/nginx.conf
deploy/hmtstc-backend.service
webhook_server.py
```

## 6. Paket 2 Kabul Kriterleri Taslagi

Package 2 should be accepted only if:

```text
[ ] Tracked credential-shaped runtime file policy is resolved.
[ ] No real API key, API secret, token or password is committed.
[ ] Deploy store example references are aligned with actual repo files.
[ ] Active frontend route/page inventory remains accurate.
[ ] Backend route inventory is documented or generated.
[ ] No live trading behavior is changed.
[ ] No Binance order submission behavior is changed.
[ ] Runtime JSON stores remain untracked.
[ ] `git diff --name-only` contains only the scoped Package 2 files.
```

## 7. Paket 2'de Kesinlikle Yapilmayacaklar

```text
Auth rewrite
Binance integration rewrite
Database migration
Live trading enablement
Real order submission changes
Frontend redesign
Deploy service rewrite
```

## 8. Final Recommendation

Start Package 2 as a repository hygiene package, not as a feature package. The highest-value first change is to remove ambiguity around credential-shaped runtime files and deploy/runtime store examples.
