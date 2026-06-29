# Level1 40.07 Frontend API Inventory

Bu rapor, frontend JavaScript dosyalarındaki API çağrılarını statik olarak çıkarır.
Sonraki `API contract diff` adımı için frontend tarafı referans setidir.

- Status: `ok`
- Generated at: `2026-06-11T19:02:28.054722+00:00`
- Frontend JS file count: `29`
- API call count: `94`
- Unique endpoint count: `77`
- Unique base path count: `74`
- Mutating call count: `51`
- Dynamic call count: `7`
- Endpoint reference count: `25`

## Required base paths

- `/api/dashboard/bundle` — OK
- `/api/settings` — OK
- `/api/auth/me` — OK
- `/api/real/readiness` — OK

## Method count

- `DELETE`: 3
- `GET`: 43
- `POST`: 48

## Top base paths

- `/api/settings`: 5
- `/api/rules`: 5
- `/api/users`: 3
- `/api/bot/status`: 3
- `/api/audit`: 3
- `/api/users/me/api-connection`: 3
- `/api/auth/me`: 2
- `/api/models/reports/export`: 2
- `/api/real/lock`: 2
- `/api/rules/save`: 2
- `/api/agent/chat`: 1
- `/api/agent/report`: 1
- `/api/dashboard/bundle`: 1
- `/api/dashboard`: 1
- `/api/positions`: 1
- `/api/history`: 1
- `/api/logs`: 1
- `/api/rules/paper-lab/status`: 1
- `/api/binance/market`: 1
- `/api/bot/last-scan`: 1
- `/api/performance`: 1
- `/api/models/reports`: 1
- `/api/intelligence/overview`: 1
- `/api/intelligence/auto-bot-mode-decision`: 1
- `/api/intelligence/tradeability-decision`: 1
- `/api/rules/examples`: 1
- `/api/audit/export`: 1
- `/api/auth/login`: 1
- `/api/auth/change-password`: 1
- `/api/auth/logout`: 1

## Runtime store policy

- Tracked runtime stores: `0`
- Unignored runtime stores: `0`
- Allowed ignored runtime stores: `2`

## Calls

| Method | Endpoint | File | Line | Kind |
|---|---|---|---:|---|
| POST | `/api/agent/chat` | `frontend/js/app/agent.js` | 131 | fetchJson |
| POST | `/api/agent/report` | `frontend/js/app/agent.js` | 187 | fetchJson |
| GET | `/api/users` | `frontend/js/app/api.js` | 461 | fetchJson |
| GET | `/api/dashboard/bundle` | `frontend/js/app/api.js` | 541 | fetchJson |
| GET | `/api/dashboard` | `frontend/js/app/api.js` | 588 | fetchJson |
| GET | `/api/positions` | `frontend/js/app/api.js` | 589 | fetchJson |
| GET | `/api/history` | `frontend/js/app/api.js` | 590 | fetchJson |
| GET | `/api/logs` | `frontend/js/app/api.js` | 591 | fetchJson |
| GET | `/api/settings` | `frontend/js/app/api.js` | 592 | fetchJson |
| GET | `/api/bot/status` | `frontend/js/app/api.js` | 593 | fetchJson |
| GET | `/api/rules` | `frontend/js/app/api.js` | 594 | fetchJson |
| GET | `/api/rules/paper-lab/status` | `frontend/js/app/api.js` | 595 | fetchJson |
| GET | `/api/binance/market?limit=100&strict=false` | `frontend/js/app/api.js` | 733 | fetchJson |
| GET | `/api/bot/last-scan` | `frontend/js/app/api.js` | 737 | fetchJson |
| GET | `/api/performance?start={dynamic}&end={dynamic}` | `frontend/js/app/api.js` | 741 | fetchJson |
| GET | `/api/auth/me` | `frontend/js/app/api.js` | 745 | fetchJson |
| GET | `/api/models/reports?period=7d` | `frontend/js/app/api.js` | 749 | fetchJson |
| GET | `/api/audit?limit=80` | `frontend/js/app/api.js` | 753 | fetchJson |
| GET | `/api/intelligence/overview` | `frontend/js/app/api.js` | 757 | fetchJson |
| GET | `/api/intelligence/auto-bot-mode-decision` | `frontend/js/app/api.js` | 761 | fetchJson |
| GET | `/api/intelligence/tradeability-decision` | `frontend/js/app/api.js` | 765 | fetchJson |
| GET | `/api/users/me/api-connection` | `frontend/js/app/api.js` | 769 | fetchJson |
| GET | `/api/rules/examples` | `frontend/js/app/api.js` | 776 | fetchJson |
| GET | `/api/users` | `frontend/js/app/api.js` | 783 | fetchJson |
| POST | `/api/audit` | `frontend/js/app/audit.js` | 25 | fetchJson |
| DELETE | `/api/audit?confirm=CLEAR_AUDIT` | `frontend/js/app/audit.js` | 50 | fetchJson |
| GET | `/api/audit/export?{dynamic}` | `frontend/js/app/audit.js` | 68 | fetchJson |
| GET | `/api/auth/me` | `frontend/js/app/auth.js` | 29 | fetchJson |
| POST | `/api/auth/login` | `frontend/js/app/auth.js` | 135 | fetchJson |
| POST | `/api/auth/change-password` | `frontend/js/app/auth.js` | 240 | fetchJson |
| POST | `/api/auth/logout` | `frontend/js/app/auth.js` | 266 | fetchJson |
| GET | `/api/bot/status` | `frontend/js/app/bot.js` | 36 | fetchJson |
| POST | `/api/bot/start?mode=paper` | `frontend/js/app/bot.js` | 49 | fetchJson |
| GET | `/api/bot/status` | `frontend/js/app/bot.js` | 53 | fetchJson |
| POST | `/api/bot/stop` | `frontend/js/app/bot.js` | 101 | fetchJson |
| POST | `/api/bot/emergency-stop?action={dynamic}` | `frontend/js/app/bot.js` | 147 | fetchJson |
| POST | `/api/bot/reset` | `frontend/js/app/bot.js` | 193 | fetchJson |
| POST | `/api/intelligence/strategy-generator/accept-draft` | `frontend/js/app/intelligence.js` | 9 | fetchJson |
| POST | `/api/models/real-approval/decision` | `frontend/js/app/realApproval.js` | 14 | fetchJson |
| POST | `/api/settings/risk-profiles/{dynamic}` | `frontend/js/app/realApproval.js` | 32 | fetchJson |
| GET | `/api/models/reports/export?period=7d&format=json` | `frontend/js/app/realApproval.js` | 44 | fetchJson |
| GET | `/api/models/reports/export?period=7d&format=csv` | `frontend/js/app/realApproval.js` | 78 | fetchJson |
| POST | `/api/models/reports/archive?period=7d` | `frontend/js/app/realApproval.js` | 96 | fetchJson |
| POST | `/api/models/real-order/dry-run` | `frontend/js/app/realApproval.js` | 108 | fetchJson |
| GET | `/api/real/readiness` | `frontend/js/app/realTrade.js` | 5 | fetchJson |
| GET | `/api/real/health` | `frontend/js/app/realTrade.js` | 6 | fetchJson |
| GET | `/api/real/positions` | `frontend/js/app/realTrade.js` | 7 | fetchJson |
| GET | `/api/real/orders` | `frontend/js/app/realTrade.js` | 8 | fetchJson |
| GET | `/api/real/pilot` | `frontend/js/app/realTrade.js` | 9 | fetchJson |
| GET | `/api/real/wallet-integrity` | `frontend/js/app/realTrade.js` | 10 | fetchJson |
| GET | `/api/real/money-separation` | `frontend/js/app/realTrade.js` | 11 | fetchJson |
| GET | `/api/real/balances/reconciliation` | `frontend/js/app/realTrade.js` | 12 | fetchJson |
| POST | `/api/real/unlock` | `frontend/js/app/realTrade.js` | 34 | fetchJson |
| POST | `/api/real/lock` | `frontend/js/app/realTrade.js` | 57 | fetchJson |
| POST | `/api/real/orders/preview` | `frontend/js/app/realTrade.js` | 76 | fetchJson |
| POST | `/api/real/orders/dry-run` | `frontend/js/app/realTrade.js` | 103 | fetchJson |
| POST | `/api/real/orders/place` | `frontend/js/app/realTrade.js` | 137 | fetchJson |
| POST | `/api/real/positions/reconcile` | `frontend/js/app/realTrade.js` | 160 | fetchJson |
| POST | `/api/real/positions/emergency-close` | `frontend/js/app/realTrade.js` | 177 | fetchJson |
| POST | `/api/real/positions/transition` | `frontend/js/app/realTrade.js` | 195 | fetchJson |
| POST | `/api/real/pilot/start` | `frontend/js/app/realTrade.js` | 217 | fetchJson |
| POST | `/api/real/pilot/stop` | `frontend/js/app/realTrade.js` | 240 | fetchJson |
| GET | `/api/real/pilot/report` | `frontend/js/app/realTrade.js` | 254 | fetchJson |
| POST | `/api/real/emergency/lock` | `frontend/js/app/realTrade.js` | 272 | fetchJson |
| GET | `/api/real/emergency/checklist` | `frontend/js/app/realTrade.js` | 287 | fetchJson |
| POST | `/api/real/emergency/recovery-unlock` | `frontend/js/app/realTrade.js` | 305 | fetchJson |
| POST | `/api/real/lock` | `frontend/js/app/realTrade.js` | 338 | fetchJson |
| GET | `/api/rules` | `frontend/js/app/rules.js` | 275 | fetchJson |
| POST | `/api/rules/get` | `frontend/js/app/rules.js` | 364 | fetchJson |
| POST | `/api/rules/save` | `frontend/js/app/rules.js` | 444 | fetchJson |
| POST | `/api/rules/delete` | `frontend/js/app/rules.js` | 516 | fetchJson |
| DELETE | `/api/rules/{dynamic}` | `frontend/js/app/rules.js` | 526 | fetchJson |
| POST | `/api/rules/selection` | `frontend/js/app/rules.js` | 604 | fetchJson |
| POST | `/api/rules/activate-paper-lab` | `frontend/js/app/rules.js` | 738 | fetchJson |
| GET | `/api/rules` | `frontend/js/app/rules.js` | 890 | fetchJson |
| GET | `/api/rules` | `frontend/js/app/rules.js` | 990 | fetchJson |
| POST | `/api/rules/save` | `frontend/js/app/rules.js` | 1006 | fetchJson |
| GET | `/api/rules` | `frontend/js/app/rules.js` | 1045 | fetchJson |
| POST | `/api/rules/auto-paper-lab` | `frontend/js/app/rules.js` | 1108 | fetchJson |
| POST | `/api/settings/coin-filter` | `frontend/js/app/settings.js` | 295 | fetchJson |
| POST | `/api/settings/risk-preview` | `frontend/js/app/settings.js` | 415 | fetchJson |
| POST | `/api/settings/risk-impact` | `frontend/js/app/settings.js` | 440 | fetchJson |
| POST | `/api/settings/rollback-preview` | `frontend/js/app/settings.js` | 457 | fetchJson |
| POST | `/api/settings/rollback` | `frontend/js/app/settings.js` | 475 | fetchJson |
| POST | `/api/settings` | `frontend/js/app/settings.js` | 515 | fetchJson |
| POST | `/api/settings/strategies` | `frontend/js/app/settings.js` | 575 | fetchJson |
| POST | `/api/users` | `frontend/js/app/users.js` | 17 | fetchJson |
| POST | `/api/users/{dynamic}/reset-password` | `frontend/js/app/users.js` | 59 | fetchJson |
| POST | `/api/users/{dynamic}/active` | `frontend/js/app/users.js` | 86 | fetchJson |
| POST | `/api/users/me/api-connection` | `frontend/js/app/users.js` | 115 | fetchJson |
| DELETE | `/api/users/me/api-connection` | `frontend/js/app/users.js` | 140 | fetchJson |
| POST | `/api/settings` | `frontend/js/pages/coinFilter.js` | 98 | fetchJson |
| GET | `/api/settings` | `frontend/js/pages/coinFilter.js` | 112 | fetchJson |
| POST | `/api/settings` | `frontend/js/pages/dashboard.js` | 53 | fetchJson |
