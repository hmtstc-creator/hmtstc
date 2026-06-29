# Level1 40.11 Real Trade Manual Review Matrix

## Ozet

- Durum: `ok`
- Critical real-trade endpoint satiri: `13`
- Manuel inceleme matrisi satiri: `13`
- Bilinmeyen real-trade risk tipi: `0`

## Contract Guard Durumu

- Missing path: `0`
- Method mismatch: `0`
- Runtime leak: `0`
- Tracked runtime store: `0`
- Unignored runtime store: `0`

## Real Trade Risk Tipleri

| Risk tipi | Adet |
|---|---:|
| `ORDER_PREVIEW_OR_DRY_RUN` | 2 |
| `ORDER_SUBMISSION` | 1 |
| `PILOT_CONTROL` | 2 |
| `POSITION_CONTROL` | 3 |
| `REAL_TRADE_LOCK_CONTROL` | 5 |

## Manuel Inceleme Matrisi

| Method | Endpoint | Dosya | Satir | Risk tipi | Owner | Readiness | Not |
|---|---|---|---:|---|---|---|---|
| `POST` | `/api/real/unlock` | `frontend/js/app/realTrade.js` | 34 | `REAL_TRADE_LOCK_CONTROL` | evet | hayir | Owner onayi ve audit gerekcesi olmadan kilit acma/kapama islemi yapilmamali. |
| `POST` | `/api/real/lock` | `frontend/js/app/realTrade.js` | 57 | `REAL_TRADE_LOCK_CONTROL` | evet | hayir | Owner onayi ve audit gerekcesi olmadan kilit acma/kapama islemi yapilmamali. |
| `POST` | `/api/real/orders/preview` | `frontend/js/app/realTrade.js` | 76 | `ORDER_PREVIEW_OR_DRY_RUN` | hayir | evet | Canli emir uretmedigi ve readiness baglamini bozmadigi manuel olarak dogrulanmali. |
| `POST` | `/api/real/orders/dry-run` | `frontend/js/app/realTrade.js` | 103 | `ORDER_PREVIEW_OR_DRY_RUN` | hayir | evet | Canli emir uretmedigi ve readiness baglamini bozmadigi manuel olarak dogrulanmali. |
| `POST` | `/api/real/orders/place` | `frontend/js/app/realTrade.js` | 137 | `ORDER_SUBMISSION` | evet | evet | Owner onayi, readiness kontrolu, dry-run kaniti ve emergency lock kapali durumu olmadan kullanilmamali. |
| `POST` | `/api/real/positions/reconcile` | `frontend/js/app/realTrade.js` | 160 | `POSITION_CONTROL` | evet | hayir | Owner onayi, pozisyon state kaniti ve gerekirse emergency gerekcesi beklenmeli. |
| `POST` | `/api/real/positions/emergency-close` | `frontend/js/app/realTrade.js` | 177 | `POSITION_CONTROL` | evet | hayir | Owner onayi, pozisyon state kaniti ve gerekirse emergency gerekcesi beklenmeli. |
| `POST` | `/api/real/positions/transition` | `frontend/js/app/realTrade.js` | 195 | `POSITION_CONTROL` | evet | hayir | Owner onayi, pozisyon state kaniti ve gerekirse emergency gerekcesi beklenmeli. |
| `POST` | `/api/real/pilot/start` | `frontend/js/app/realTrade.js` | 217 | `PILOT_CONTROL` | evet | hayir | Owner onayi ve pilot limitleri belgelenmeden pilot baslatma/durdurma yapilmamali. |
| `POST` | `/api/real/pilot/stop` | `frontend/js/app/realTrade.js` | 240 | `PILOT_CONTROL` | evet | hayir | Owner onayi ve pilot limitleri belgelenmeden pilot baslatma/durdurma yapilmamali. |
| `POST` | `/api/real/emergency/lock` | `frontend/js/app/realTrade.js` | 272 | `REAL_TRADE_LOCK_CONTROL` | evet | hayir | Owner onayi ve audit gerekcesi olmadan kilit acma/kapama islemi yapilmamali. |
| `POST` | `/api/real/emergency/recovery-unlock` | `frontend/js/app/realTrade.js` | 305 | `REAL_TRADE_LOCK_CONTROL` | evet | hayir | Owner onayi ve audit gerekcesi olmadan kilit acma/kapama islemi yapilmamali. |
| `POST` | `/api/real/lock` | `frontend/js/app/realTrade.js` | 338 | `REAL_TRADE_LOCK_CONTROL` | evet | hayir | Owner onayi ve audit gerekcesi olmadan kilit acma/kapama islemi yapilmamali. |

## Owner Onay Beklentileri

- `ORDER_SUBMISSION`: owner onayi, readiness, once dry-run, emergency lock kapali olmasi beklenir.
- `ORDER_PREVIEW_OR_DRY_RUN`: order gondermemesi ve readiness baglaminda kalmasi beklenir.
- `POSITION_CONTROL`: owner onayi, pozisyon state kaniti ve emergency-close icin gerekce beklenir.
- `REAL_TRADE_LOCK_CONTROL`: owner onayi ve audit gerekcesi beklenir.
- `PILOT_CONTROL`: owner onayi ve pilot limitlerinin belgelenmesi beklenir.

## Blocker / Review Listesi

Blocker veya review item yok.

## Sonuc

Real-trade kritik endpointleri icin manuel inceleme matrisi uretildi ve risk tipi bilinmeyen endpoint yok.

## Paket 7 Icin Onerilen Devam

- Use this matrix before any live-trade package or owner approval workflow change.
- Verify ORDER_SUBMISSION endpoints require owner approval, readiness, prior dry-run and emergency-lock clear state.
- Verify POSITION_CONTROL endpoints require owner approval and current position state evidence.
- Keep real-trade route and executor behavior changes out of audit-only packages.
