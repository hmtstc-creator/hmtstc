# Frontend Active Surface

## 1. Entry Point

Active frontend entrypoint:

```text
frontend/index.html
```

The page mounts into:

```text
<div id="root"></div>
```

## 2. CSS Zinciri

Loaded CSS:

```text
frontend/css/styles.css
frontend/css/dashboard-funnel.css
```

## 3. Config/Data/UI Zinciri

Loaded before page/app modules:

```text
frontend/js/config.js
frontend/js/data.js
frontend/js/ui.js
frontend/js/pages/base.js
```

Key behavior:

- `config.js` sets local API base to `http://127.0.0.1:8000`.
- non-local API base is `http://178.105.40.99`.
- `data.js` creates `HMTSTC_DATA`.
- `ui.js` provides shared rendering helpers.

## 4. Active Pages

Loaded page files:

```text
frontend/js/pages/settings.js
frontend/js/pages/coinFilter.js
frontend/js/pages/ruleEditor.js
frontend/js/pages/users.js
frontend/js/pages/strategies.js
frontend/js/pages/dashboard.js
frontend/js/pages/admin.js
```

The active menu in `frontend/js/data.js` includes:

```text
dashboard
settings
coinFilter
ruleEditor
strategies
users
admin
```

## 5. Active App Modules

Loaded app modules:

```text
frontend/js/app/state.js
frontend/js/app/api.js
frontend/js/app/auth.js
frontend/js/app/settings.js
frontend/js/app/bot.js
frontend/js/app/agent.js
frontend/js/app/rules.js
frontend/js/app/users.js
frontend/js/app/audit.js
frontend/js/app/realApproval.js
frontend/js/app/realTrade.js
frontend/js/app/intelligence.js
frontend/js/app/render.js
frontend/js/app.js
frontend/js/app/init.js
```

`frontend/js/app.js` merges module objects onto `window.HMTSTC_APP`. `frontend/js/app/init.js` loads last.

## 6. Stub / Legacy Candidates

Package 2 decisions:

```text
frontend/js/pages.js local repo icinde yoktur; Paket 2'de silinecek bir dosya degildir.
frontend/js/pages/backups.js unloaded stub olarak kalir.
frontend/js/app/backups.js unloaded stub olarak kalir.
Frontend functional behavior Paket 2'de degistirilmemistir.
```

## 7. Paket 2 Karari

Paket 2 frontend module creation package degildir. Active frontend surface documented only; no JS, CSS or HTML behavior was changed.

## 8. Paket 3 Contract Guard Karari

Paket 3 ile frontend API inventory parser yalnizca gercek `fetchJson(...)` ve `fetch(...)` cagri argumanlarini API call sayacak sekilde sertlestirildi. `auditAction` metadata icindeki `endpoint: "/api/..."` stringleri call listesine girmez; `endpoint_references` olarak ayrilir. Dynamic concat endpointler `{dynamic}` placeholder ile normalize edilir.

Generated frontend contract reports:

```text
docs/LEVEL1_40_07_FRONTEND_API_INVENTORY.json
docs/LEVEL1_40_07_FRONTEND_API_INVENTORY.md
```
