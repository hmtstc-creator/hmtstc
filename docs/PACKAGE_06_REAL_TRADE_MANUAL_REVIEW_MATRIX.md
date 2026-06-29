# Paket 6 Real Trade Manual Review Matrix

## 1. Paket amaci

Paket 6, Paket 5 ile `CRITICAL_REAL_TRADE` olarak isaretlenen endpointler icin read-only manuel inceleme matrisi uretir. Amac, canli islemle ilgili kritik endpointlerin hangi frontend dosyasindan cagrildigini, hangi risk tipine girdigini ve hangi owner onay beklentileriyle ele alinmasi gerektigini dokumante etmektir.

Paket 6 canlı işlem davranışını değiştirmedi. Sadece Paket 5 ile işaretlenen CRITICAL_REAL_TRADE endpointleri için read-only manuel inceleme matrisi ve owner onay beklentisi raporu üretti.

## 2. Hangi raporlar kullanildi?

Kullanilan ana kaynaklar:

- `docs/LEVEL1_40_10_MUTATING_ENDPOINT_SAFETY_AUDIT.json`
- `docs/LEVEL1_40_08_API_CONTRACT_DIFF.json`

40.10 raporundaki `critical_real_trade` listesi matrise donusturuldu. Contract diff tarafindan missing path, method mismatch ve runtime store guvenlik sayilari kontrol edildi.

## 3. Real trade risk tipleri

40.11 scripti su risk tiplerini uretir:

- `ORDER_SUBMISSION`
- `ORDER_PREVIEW_OR_DRY_RUN`
- `POSITION_CONTROL`
- `REAL_TRADE_LOCK_CONTROL`
- `PILOT_CONTROL`
- `UNKNOWN_REAL_TRADE_RISK_TYPE`

Final raporda `UNKNOWN_REAL_TRADE_RISK_TYPE` sayisi `0` oldu.

## 4. Owner onay beklentileri

- `ORDER_SUBMISSION`: owner onayi, readiness, once dry-run, emergency lock kapali durumu.
- `ORDER_PREVIEW_OR_DRY_RUN`: order gondermemesi ve readiness baglami.
- `POSITION_CONTROL`: owner onayi, pozisyon state kaniti, emergency-close icin gerekce.
- `REAL_TRADE_LOCK_CONTROL`: owner onayi ve audit gerekcesi.
- `PILOT_CONTROL`: owner onayi ve pilot limitleri.

## 5. Degistirilen dosyalar

- `scripts/level1_40_11_real_trade_manual_review_matrix.py`
- `docs/LEVEL1_40_11_REAL_TRADE_MANUAL_REVIEW_MATRIX.json`
- `docs/LEVEL1_40_11_REAL_TRADE_MANUAL_REVIEW_MATRIX.md`
- `docs/PACKAGE_06_REAL_TRADE_MANUAL_REVIEW_MATRIX.md`
- `README.md`
- `todo.md`

Contract guard ve Paket 5 audit raporlari test sirasinda yeniden uretildi.

## 6. Dokunulmayan kritik dosyalar

Su kritik dosyalara dokunulmadi:

- `backend/routes/real_routes.py`
- `backend/services/*order*`
- `backend/services/*executor*`
- `backend/services/*binance*`
- `backend/binance_credentials_store.json`
- `backend/settings_store.json`
- `backend/shadow_store.json`
- `deploy/*`
- `webhook_server.py`
- `frontend/js/app/realTrade.js`
- `frontend/js/app/realApproval.js`

## 7. Test sonuclari

- `py -X pycache_prefix=.pycache_paket6 -m py_compile backend\main.py webhook_server.py scripts\level1_40_07_frontend_api_inventory.py scripts\level1_40_08_api_contract_diff.py scripts\level1_40_09_missing_endpoint_report.py scripts\level1_40_10_mutating_endpoint_safety_audit.py scripts\level1_40_11_real_trade_manual_review_matrix.py`: pass
- `py scripts\level1_40_06_api_route_inventory.py`: pass, `route_count=891`
- `py scripts\level1_40_07_frontend_api_inventory.py`: pass, `call_count=87`, `unique_base_path_count=72`
- `py scripts\level1_40_08_api_contract_diff.py --strict`: pass, `missing_path_count=0`, `method_mismatch_count=0`
- `py scripts\level1_40_09_missing_endpoint_report.py`: pass, `true_blocker_count=0`, `parser_gap_or_false_positive_count=0`
- `py scripts\level1_40_10_mutating_endpoint_safety_audit.py`: pass, `status=ok`, `mutating_call_count=50`, `unclassified_mutating_count=0`, `special_review_required_count=13`
- `py scripts\level1_40_11_real_trade_manual_review_matrix.py`: pass, `status=ok`, `critical_real_trade_count=13`, `review_matrix_count=13`, `unknown_real_trade_risk_type_count=0`
- `node --check frontend\js\pages\dashboard.js`: calistirilamadi, Node PATH'te yok

## 8. Paket 7'ye gecis karari

40.06-40.11 kalite zinciri temiz kaldigi ve unknown real-trade risk tipi `0` oldugu surece Paket 7'ye gecis uygundur.
