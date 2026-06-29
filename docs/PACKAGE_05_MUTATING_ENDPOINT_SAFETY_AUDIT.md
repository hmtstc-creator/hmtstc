# Paket 5 Mutating Endpoint Safety Audit

## Paket 5 amaci

Paket 5, frontend tarafindan cagrilan mutating API endpointlerini guvenlik siniflarina ayirmak ve her paket oncesi calistirilabilecek read-only kalite kapisi olusturmak icin tamamlandi.

Bu paket yeni trading ozelligi eklemez. Amac canli islem, bot kontrol, kullanici secret/izinleri, ayar/risk/kural kayitlari ve model onay akislari gibi mutating yuzeyleri gorunur hale getirmektir.

## Hangi dosyalar degisti

- `scripts/level1_40_10_mutating_endpoint_safety_audit.py`
- `docs/LEVEL1_40_10_MUTATING_ENDPOINT_SAFETY_AUDIT.json`
- `docs/LEVEL1_40_10_MUTATING_ENDPOINT_SAFETY_AUDIT.md`
- `docs/PACKAGE_05_MUTATING_ENDPOINT_SAFETY_AUDIT.md`
- `README.md`
- `todo.md`

Contract guard scriptleri calistirildigi icin 40.06, 40.07, 40.08 ve 40.09 raporlari da yeniden uretildi.

## Canli islem mantigina dokunulmadigi

Bu paket sadece mevcut JSON contract raporlarini okuyan yeni bir audit scripti ekledi. Asagidaki alanlara dokunulmadi:

- `backend/routes/real_routes.py`
- `backend/services/*order*`
- `backend/services/*executor*`
- `backend/services/*binance*`
- Runtime store dosyalari
- `deploy/*`
- `webhook_server.py`
- Canli emir gonderme akisi
- Binance baglanti akisi
- Futures akisi
- Bot start/stop calisma mantigi
- Karabasan, strateji ve filtre karar motoru

## Endpoint kategorileri

40.10 audit scripti frontend inventory icindeki `mutating=true` cagrilari su kategorilere ayirir:

- `CRITICAL_REAL_TRADE`
- `HIGH_BOT_CONTROL`
- `HIGH_USER_SECRET_OR_PERMISSION`
- `MEDIUM_SETTINGS_RISK_RULES`
- `MEDIUM_MODEL_APPROVAL_OR_REPORT`
- `LOW_AUDIT_AUTH_AGENT`
- `UNCLASSIFIED_MUTATING`

Real-trade namespace icindeki mutating endpointler muhafazakar olarak `CRITICAL_REAL_TRADE` ozel inceleme listesine alinir. Bu endpointlerin varligi tek basina hata degildir, ancak canli islem paketleri oncesinde manuel review gerektirir.

## Test sonuclari

- `py -m py_compile backend\main.py webhook_server.py scripts\level1_40_07_frontend_api_inventory.py scripts\level1_40_08_api_contract_diff.py scripts\level1_40_09_missing_endpoint_report.py scripts\level1_40_10_mutating_endpoint_safety_audit.py`: pass
- `py scripts\level1_40_06_api_route_inventory.py`: pass, `route_count=891`
- `py scripts\level1_40_07_frontend_api_inventory.py`: pass, `call_count=87`, `unique_base_path_count=72`
- `py scripts\level1_40_08_api_contract_diff.py --strict`: pass, `missing_path_count=0`, `method_mismatch_count=0`
- `py scripts\level1_40_09_missing_endpoint_report.py`: pass, `true_blocker_count=0`, `parser_gap_or_false_positive_count=0`
- `py scripts\level1_40_10_mutating_endpoint_safety_audit.py`: pass, `status=ok`, `mutating_call_count=50`, `unclassified_mutating_count=0`, `special_review_required_count=13`
- `node --check frontend\js\pages\dashboard.js`: calistirilamadi, Node PATH'te yok

## Paket 6'ya gecis karari

Contract guard ve 40.10 audit temiz kaldigi surece Paket 6'ya gecis uygundur.
