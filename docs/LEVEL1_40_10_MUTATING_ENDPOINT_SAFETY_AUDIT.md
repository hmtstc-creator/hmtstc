# Level1 40.10 Mutating Endpoint Safety Audit

## Ozet

- Durum: `ok`
- Frontend API cagrisi: `94`
- Mutating cagri: `51`
- Siniflandirilan mutating cagri: `51`
- Unclassified mutating cagri: `0`
- Ozel real-trade inceleme sayisi: `13`

## Contract Guard Durumu

- Missing path: `0`
- Method mismatch: `0`
- Runtime leak: `0`
- Tracked runtime store: `0`
- Unignored runtime store: `0`

## Mutating Endpoint Kategorileri

| Kategori | Adet |
|---|---:|
| `CRITICAL_REAL_TRADE` | 13 |
| `HIGH_BOT_CONTROL` | 4 |
| `HIGH_USER_SECRET_OR_PERMISSION` | 5 |
| `LOW_AUDIT_AUTH_AGENT` | 7 |
| `MEDIUM_MODEL_APPROVAL_OR_REPORT` | 4 |
| `MEDIUM_SETTINGS_RISK_RULES` | 18 |

## Critical Real Trade Ozel Inceleme

| Method | Endpoint | Dosya | Satir | Sebep |
|---|---|---|---:|---|
| `POST` | `/api/real/unlock` | `frontend/js/app/realTrade.js` | 34 | Matched safety rule /api/real/unlock |
| `POST` | `/api/real/lock` | `frontend/js/app/realTrade.js` | 57 | Matched safety rule /api/real/lock |
| `POST` | `/api/real/orders/preview` | `frontend/js/app/realTrade.js` | 76 | Conservative real-trade namespace review |
| `POST` | `/api/real/orders/dry-run` | `frontend/js/app/realTrade.js` | 103 | Conservative real-trade namespace review |
| `POST` | `/api/real/orders/place` | `frontend/js/app/realTrade.js` | 137 | Matched safety rule /api/real/orders/place |
| `POST` | `/api/real/positions/reconcile` | `frontend/js/app/realTrade.js` | 160 | Conservative real-trade namespace review |
| `POST` | `/api/real/positions/emergency-close` | `frontend/js/app/realTrade.js` | 177 | Matched safety rule /api/real/positions/emergency-close |
| `POST` | `/api/real/positions/transition` | `frontend/js/app/realTrade.js` | 195 | Matched safety rule /api/real/positions/transition |
| `POST` | `/api/real/pilot/start` | `frontend/js/app/realTrade.js` | 217 | Matched safety rule /api/real/pilot/start |
| `POST` | `/api/real/pilot/stop` | `frontend/js/app/realTrade.js` | 240 | Matched safety rule /api/real/pilot/stop |
| `POST` | `/api/real/emergency/lock` | `frontend/js/app/realTrade.js` | 272 | Matched safety rule /api/real/emergency/lock |
| `POST` | `/api/real/emergency/recovery-unlock` | `frontend/js/app/realTrade.js` | 305 | Matched safety rule /api/real/emergency/recovery-unlock |
| `POST` | `/api/real/lock` | `frontend/js/app/realTrade.js` | 338 | Matched safety rule /api/real/lock |

## Unclassified Mutating Endpointler

Unclassified mutating endpoint yok.

## Runtime Store Guvenligi

Runtime store leak, tracked runtime store veya unignored runtime store yok.

## Sonuc

Mutating endpointler guvenlik siniflarina ayrildi ve contract guard temiz.

Review listesi:
- Critical real-trade mutating endpoint count is 13; special review required

## Paket 6 Icin Onerilen Devam

- Keep this audit in the package quality sequence after the API contract diff.
- Review CRITICAL_REAL_TRADE items manually before any live-trade package.
- Add every new mutating frontend API call to a safety category before merging.
- Keep runtime stores ignored and untracked.
