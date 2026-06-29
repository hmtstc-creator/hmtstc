# PACKAGE 02 - Repo Hygiene and Contract Clarity

## 1. Paket Amaci

Paket 2 repository hygiene, runtime store policy and API/frontend contract clarity paketidir. Bu paket yeni trading ozelligi eklemez ve live trading davranisini degistirmez.

## 2. Paket 1 Karar Ozeti

Paket 1 sunlari netlestirdi:

- Repo artik erken mock-only sistem degildir.
- Auth, rol yonetimi, Binance/Futures, real-trade, production ve quality route yuzeyleri vardir.
- `frontend/index.html` aktif frontend entrypoint dosyasidir.
- `frontend/js/pages.js` local repoda yoktur.
- `backend/binance_credentials_store.json` tracked ve credential-shaped store durumundaydi.
- Deploy script `settings_store.example.json` ve `shadow_store.example.json` bekliyordu.

## 3. Credential Store Baslangic Durumu

Baslangicta:

```text
git ls-files backend/binance_credentials_store.json
=> backend/binance_credentials_store.json
```

Dosyada credential-shaped demo alanlari vardi ve raporlarda yalnizca maskeli ele alindi:

```text
api_key: demo***3456
api_secret: demo***3456
environment: mainnet
```

Paket 2 karari: Bu dosya runtime-only kabul edilir ve Git tarafindan takip edilmemelidir.

## 4. .gitignore Guncellemesi

`.gitignore` runtime credential/state store policy ile guncellendi:

```text
backend/binance_credentials_store.json
backend/settings_store.json
backend/shadow_store.json
backend/auth_store.json
backend/rule_store.json
backend/audit_store.json
backend/real_trade_store.json
backend/*_store.runtime.json
```

## 5. Example Store Dosyalari

Sanitize example files added:

```text
backend/binance_credentials_store.example.json
backend/settings_store.example.json
backend/shadow_store.example.json
```

These files contain placeholders only and do not contain real API keys, secrets, tokens or user data.

## 6. Deploy Example Uyumu

`deploy/deploy.sh` was not changed. Its existing expectation for:

```text
backend/settings_store.example.json
backend/shadow_store.example.json
```

is now satisfied by tracked sanitized example files.

## 7. API Contract Inventory

`docs/API_CONTRACT_INVENTORY.md` was created from the current route surface. It records:

- backend entrypoint
- app-level endpoints
- router list
- auth shape
- frontend-facing endpoints
- owner/admin endpoints
- Binance/Futures/Real Trade risk surface

Observed route decorator count remains 959 across `backend/routes/*.py`.

## 8. Frontend Active Surface

`docs/FRONTEND_ACTIVE_SURFACE.md` was created. It records:

- active entrypoint
- CSS chain
- config/data/UI chain
- active pages
- active app modules
- unloaded stubs and non-existent `frontend/js/pages.js`

No frontend behavior was changed.

## 9. Degistirilen Dosyalar

Allowed source/doc files changed or added:

```text
.gitignore
README.md
todo.md
backend/binance_credentials_store.example.json
backend/settings_store.example.json
backend/shadow_store.example.json
docs/ACTIVE_LEGACY_MAP.md
docs/STORE_POLICY.md
docs/API_CONTRACT_INVENTORY.md
docs/FRONTEND_ACTIVE_SURFACE.md
docs/PACKAGE_02_REPO_HYGIENE_AND_CONTRACT.md
```

Expected Git index change:

```text
backend/binance_credentials_store.json removed from Git tracking with git rm --cached
```

## 10. Test Sonuclari

Executed checks:

| Check | Result | Note |
| --- | --- | --- |
| `git status --short --untracked-files=all` | Pass with note | Package 2 files visible; `Paketler/paket2.md` is a pre-existing user working-tree change outside Package 2 product scope |
| `git diff --name-only` | Pass with note | Allowed modified tracked files plus user `Paketler/paket2.md`; new untracked Package 2 files shown by `git status` |
| `git diff --cached --name-only` | Pass | Shows `backend/binance_credentials_store.json` removed from index |
| `git check-ignore -v backend/binance_credentials_store.json backend/settings_store.json backend/shadow_store.json` | Pass | All three files are ignored by `.gitignore` |
| `git ls-files backend/binance_credentials_store.json ...example.json` | Pass | Runtime credential store no longer listed; new example files are untracked until added |
| `Test-Path backend/binance_credentials_store.json` | Pass | Runtime file remains on local disk |
| Example store placeholder check | Pass | `REPLACE_WITH_*`, `testnet`, `live_trading_default: false`, `emergency_stop: true` present |
| Sensitive demo/mainnet grep on example/docs package files | Pass | No `demo_api_key`, `demo_secret`, `GERCEK PARA`, `mainnet_guard` or long token-like values found |
| `py -m py_compile backend/main.py webhook_server.py` | Pass | Syntax compile completed |

Known working tree note:

- `Paketler/paket2.md` is modified but was not changed by the Package 2 product edits. It should be reviewed separately by the user before commit selection.

## 11. Paket 3'e Gecis Karari

Paket 3'e gecis: **Yes, after verification**.

Paket 3 feature work veya deeper safety work olabilir, ancak real-trade/Binance/order behavior sadece dedicated safety package icinde degistirilmelidir.

Paket 2 tamamlandi. Credential-shaped tracked runtime store politikasi duzeltildi, backend/binance_credentials_store.json Git takibinden cikarildi veya zaten takip edilmedigi dogrulandi, sanitize example store dosyalari eklendi, .gitignore runtime store politikasina gore guncellendi, deploy example store beklentisi karsilandi, API contract ve frontend active surface dokumanlari olusturuldu. Backend route/service, Binance, real-trade, deploy service ve frontend davranisi degistirilmedi. Paket 3'e gecis icin repository hygiene zemini guvenli hale getirildi.
