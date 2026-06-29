# PACKAGE 03 - API Contract Guard

## 1. Paket Amaci

Paket 3, Paket 1 ve Paket 2 sonrasinda API/Frontend sozlesmesini tekrar uretilebilir kalite kapisina donusturur. Bu paket urun davranisi degistirmez; backend route, backend service, frontend runtime, deploy, Binance, Futures veya real-trade logic degistirilmedi.

## 2. Paket 1 ve Paket 2 Karar Ozeti

- Paket 1 mevcut frontend/backend/deploy mimarisini ve aktif/legacy ayrimini raporladi.
- Paket 2 runtime store policy, sanitize example store dosyalari ve API/frontend contract dokumantasyonunu ekledi.
- Runtime store dosyalari localde bulunabilir, ancak ignored ve untracked olmalidir.
- `backend/binance_credentials_store.json`, `backend/settings_store.json` ve `backend/shadow_store.json` Git tarafindan takip edilmemelidir.

## 3. Baslangic Problemi

Paket 3 basinda mevcut guard scriptleri su false-positive risklerini uretiyordu:

- 40.07 ignored local `backend/shadow_store.json` dosyasini runtime leak gibi goruyordu.
- 40.07 `/api/summary` endpointini frontend required call sayiyordu.
- 40.07 `auditAction` metadata icindeki endpoint stringlerini gercek API call olarak sayabiliyordu.
- 40.07 dynamic concat endpointleri eksik/parcali yakaliyordu.
- 40.08 runtime store varligini leak gibi degerlendiriyordu.
- 40.09 rapor metninde mismatch sayisi hardcoded yazilabiliyordu.

## 4. Store Policy Uyum Duzeltmeleri

`scripts/level1_40_07_frontend_api_inventory.py` ve `scripts/level1_40_08_api_contract_diff.py` runtime store kontrolu Paket 2 policy ile uyumlu hale getirildi.

Yeni karar:

```text
tracked_runtime_stores -> blocker
unignored_runtime_stores -> blocker/review
allowed_ignored_runtime_stores -> OK
```

Uretilen raporlarda local ve ignored runtime dosyalari allowed listesinde gorunur:

```text
backend/binance_credentials_store.json
backend/shadow_store.json
```

## 5. Frontend API Parser Duzeltmeleri

40.07 artik tum `/api/...` string literal'larini call saymaz. Sadece gercek `fetchJson(...)` ve `fetch(...)` cagri argumanlari API call sayilir.

`auditAction` metadata stringleri call listesinden ayrildi:

```text
endpoint_reference_count=19
```

`/api/summary` frontend required call listesinden cikarildi. Backend critical route olarak 40.06 envanterinde kalir.

## 6. Dynamic Endpoint Matching Duzeltmeleri

Dynamic frontend endpointleri `{dynamic}` placeholder ile normalize edilir:

```text
POST /api/settings/risk-profiles/{dynamic}
DELETE /api/rules/{dynamic}
```

40.08 matcher bu dynamic frontend pathleri backend parameterized route'larla eslestirir.

## 7. Uretilen Contract Raporlari

```text
docs/LEVEL1_40_06_API_ROUTE_INVENTORY.json
docs/LEVEL1_40_06_API_ROUTE_INVENTORY.md
docs/LEVEL1_40_07_FRONTEND_API_INVENTORY.json
docs/LEVEL1_40_07_FRONTEND_API_INVENTORY.md
docs/LEVEL1_40_08_API_CONTRACT_DIFF.json
docs/LEVEL1_40_08_API_CONTRACT_DIFF.md
docs/LEVEL1_40_09_MISSING_ENDPOINT_REPORT.json
docs/LEVEL1_40_09_MISSING_ENDPOINT_REPORT.md
```

## 8. Test Sonuclari

| Check | Result |
| --- | --- |
| `py -m py_compile backend/main.py webhook_server.py scripts/level1_40_07_frontend_api_inventory.py scripts/level1_40_08_api_contract_diff.py scripts/level1_40_09_missing_endpoint_report.py` | Pass |
| `git check-ignore -v backend/binance_credentials_store.json backend/settings_store.json backend/shadow_store.json` | Pass |
| `git ls-files backend/binance_credentials_store.json backend/settings_store.json backend/shadow_store.json` | Pass, empty output |
| `py scripts/level1_40_06_api_route_inventory.py` | `LEVEL1_40_06_API_ROUTE_INVENTORY_OK`, route_count=891 |
| `py scripts/level1_40_07_frontend_api_inventory.py` | `LEVEL1_40_07_FRONTEND_API_INVENTORY_OK`, call_count=87 |
| `py scripts/level1_40_08_api_contract_diff.py --strict` | `LEVEL1_40_08_API_CONTRACT_DIFF_OK`, status=ok, missing_path_count=0, method_mismatch_count=0 |
| `py scripts/level1_40_09_missing_endpoint_report.py` | `LEVEL1_40_09_MISSING_ENDPOINT_REPORT_OK`, true_blocker_count=0 |

## 9. Degistirilen Dosyalar

```text
scripts/level1_40_07_frontend_api_inventory.py
scripts/level1_40_08_api_contract_diff.py
scripts/level1_40_09_missing_endpoint_report.py
docs/LEVEL1_40_06_API_ROUTE_INVENTORY.json
docs/LEVEL1_40_06_API_ROUTE_INVENTORY.md
docs/LEVEL1_40_07_FRONTEND_API_INVENTORY.json
docs/LEVEL1_40_07_FRONTEND_API_INVENTORY.md
docs/LEVEL1_40_08_API_CONTRACT_DIFF.json
docs/LEVEL1_40_08_API_CONTRACT_DIFF.md
docs/LEVEL1_40_09_MISSING_ENDPOINT_REPORT.json
docs/LEVEL1_40_09_MISSING_ENDPOINT_REPORT.md
docs/PACKAGE_03_API_CONTRACT_GUARD.md
docs/API_CONTRACT_INVENTORY.md
docs/FRONTEND_ACTIVE_SURFACE.md
README.md
todo.md
```

## 10. Dokunulmayan Kritik Dosyalar

```text
backend/main.py
backend/routes/*.py
backend/services/*.py
backend/core/*.py
frontend/index.html
frontend/js/app/*.js
frontend/js/pages/*.js
frontend/js/app.js
frontend/js/config.js
frontend/js/data.js
frontend/js/ui.js
frontend/css/*.css
deploy/*
webhook_server.py
backend/*_store.json runtime files
backend/*.example.json
```

## 11. Paket 4'e Gecis Karari

Paket 4'e gecis: **Yes**.

API/Frontend contract guard zemini guvenli hale getirildi. Sonraki paket feature veya safety kapsami acacaksa contract guard yeniden calistirilmalidir.

Paket 3 tamamlandi. API contract guard scriptleri Paket 2 runtime store policy ile uyumlu hale getirildi, frontend API inventory parser false-positive uretmeyecek sekilde sertlestirildi, dynamic endpointler {dynamic} placeholder ile backend parameterized route'lara eslestirildi, contract raporlari uretildi ve missing endpoint / method mismatch blokaji kalmadi. Backend route/service, frontend runtime davranisi, deploy dosyalari, Binance, Futures ve real-trade davranisi degistirilmedi. Paket 4'e gecis icin API/Frontend contract zemini guvenli hale getirildi.
