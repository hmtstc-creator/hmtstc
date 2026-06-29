# Paket 9 Rule Backend Stability

## 1. Paket amaci

Paket 9, `/api/rules/activate-paper-lab`, rule save/get/delete endpointleri ve audit/log hata izolasyonu icin backend hata yuzeyini stabilize eder.

Paket 9 canlı işlem davranışını değiştirmedi. Sadece Rules ve Paper Lab backend hata yüzeyini, payload güvenliğini ve response contract tutarlılığını stabilize etti.

## 2. Paket 8 sonrasi neden gerekli?

Paket 8 frontend secim draft'ini korudu ve backend response secimini dogruladi. Paket 9, ayni akisin backend tarafinda bos/gecersiz payload, gecersiz rule id, eksik rule ve audit/log yazma hatalarinda anlasilir HTTP detail donmesini saglar.

## 3. Degisen dosyalar

- `backend/routes/rule_routes.py`
- `backend/services/rule_engine.py`
- `frontend/js/app/rules.js`
- `scripts/level1_40_14_rule_backend_stability_audit.py`
- `docs/LEVEL1_40_14_RULE_BACKEND_STABILITY_AUDIT.json`
- `docs/LEVEL1_40_14_RULE_BACKEND_STABILITY_AUDIT.md`
- `docs/PACKAGE_09_RULE_BACKEND_STABILITY.md`
- `README.md`
- `todo.md`

Rule engine tarafında model kombinasyon matematiği değiştirilmedi; yalnızca input normalize, hata mesajı ve response shape güvenliği iyileştirildi.

## 4. Activate Paper Lab backend stabilitesi

`/api/rules/activate-paper-lab` icin:

- Payload `None` veya object disi ise guvenli `{}` olarak ele alinir.
- `selected_filter_ids` ve `selected_strategy_ids` list degilse `None` sayilir.
- ID listeleri string, trim ve unique normalize edilir.
- Explicit bos filtre/strateji listesi HTTP 400 doner.
- Gecersiz filtre/strateji ID HTTP 400 detail ile doner.
- Beklenmeyen hata HTTP 500 detail ile doner.
- Response `selected_filter_ids`, `selected_strategy_ids`, `model_count` ve `activation` alanlarini garanti eder.

## 5. Rule save/get/delete contract

`/api/rules/save` icin payload, `rule`, `rule.id` ve `rule.type` validation eklendi.

`/api/rules/get` icin bos `rule_id` HTTP 400, bulunamayan rule HTTP 404, beklenmeyen hata HTTP 500 detail doner.

`/api/rules/delete` ve `DELETE /api/rules/{rule_id}` icin bos id HTTP 400, bulunamayan rule HTTP 404, basarili response `deleted=true` ve `rule_id` doner.

## 6. Audit/log izolasyonu

Backend route tarafinda audit/log yazma hatasi `_safe_append_audit` ile izole edildi. Audit yazilamazsa ana save/delete sonucu bozulmaz ve response warning donebilir.

Frontend `rules.js` tarafinda rule save/delete/auto Paper Lab auditAction hatalari ana basari sonucunu bozmayacak sekilde try/catch icine alindi.

## 7. Backend davranisi degisti mi?

Canli emir, Binance, Futures, Karabasan, bot start/stop, strateji/filter karar motoru ve Paper Lab kombinasyon matematiği degismedi. Degisiklik sadece validation, hata mesaji, response shape ve audit izolasyonu ile sinirlidir.

## 8. Dokunulmayan kritik dosyalar

Su kritik alanlara dokunulmadi:

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

## 9. Test sonuclari

- `py -X pycache_prefix=.pycache_paket9 -m py_compile backend\main.py webhook_server.py backend\routes\rule_routes.py backend\services\rule_engine.py scripts\level1_40_07_frontend_api_inventory.py scripts\level1_40_08_api_contract_diff.py scripts\level1_40_09_missing_endpoint_report.py scripts\level1_40_10_mutating_endpoint_safety_audit.py scripts\level1_40_11_real_trade_manual_review_matrix.py scripts\level1_40_12_owner_approval_contract_audit.py scripts\level1_40_13_rule_selection_persistence_audit.py scripts\level1_40_14_rule_backend_stability_audit.py`: pass
- `py scripts\level1_40_06_api_route_inventory.py`: pass, `route_count=891`
- `py scripts\level1_40_07_frontend_api_inventory.py`: pass, `call_count=87`, `unique_base_path_count=72`
- `py scripts\level1_40_08_api_contract_diff.py --strict`: pass, `missing_path_count=0`, `method_mismatch_count=0`
- `py scripts\level1_40_09_missing_endpoint_report.py`: pass, `true_blocker_count=0`, `parser_gap_or_false_positive_count=0`
- `py scripts\level1_40_10_mutating_endpoint_safety_audit.py`: pass, `status=ok`, `mutating_call_count=50`, `unclassified_mutating_count=0`
- `py scripts\level1_40_11_real_trade_manual_review_matrix.py`: pass, `status=ok`, `critical_real_trade_count=13`, `unknown_real_trade_risk_type_count=0`
- `py scripts\level1_40_12_owner_approval_contract_audit.py`: pass, `status=ok`, `order_submission_contract_ok=true`
- `py scripts\level1_40_13_rule_selection_persistence_audit.py`: pass, `status=ok`, `draft_preserved_on_error=true`
- `py scripts\level1_40_14_rule_backend_stability_audit.py`: pass, `status=ok`, `activate_paper_lab_route_present=true`, `activate_payload_normalization_present=true`, `rule_save_validation_present=true`, `rule_get_validation_present=true`, `rule_delete_validation_present=true`, `audit_failure_isolated=true`
- `node --check frontend\js\app\rules.js`: calistirilamadi, Node PATH'te yok
- `node --check frontend\js\pages\dashboard.js`: calistirilamadi, Node PATH'te yok

Manuel kabul testi:

1. Dashboard acilir.
2. Filtre ve strateji secimi yapilir.
3. Kaydet'e basilir.
4. Backend basariliysa `selected_filter_ids` ve `selected_strategy_ids` response icinde doner.
5. Response secimleri frontend snapshot ile ayni kalir.
6. Bos filtre veya bos strateji gonderilirse backend 400 dondurur.
7. Gecersiz rule id gonderilirse backend 400/404 net detail dondurur.
8. Backend hata uretirse frontend draft secimi korur.
9. Audit/log yazilamazsa ana Paper Lab save sonucu bozulmaz.

## 10. Paket 10'a gecis karari

40.06-40.14 kalite zinciri temiz kaldigi, contract guard temiz oldugu ve runtime leak bulunmadigi surece Paket 10'a gecis uygundur.
