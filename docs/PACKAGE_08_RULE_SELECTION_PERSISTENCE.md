# Paket 8 Rule Selection Persistence

## 1. Paket amaci

Paket 8, Dashboard uzerindeki Strateji / Filtre secimlerinin kaybolmasini, eskiye donmesini veya backend explicit bos secim varken tum aktif rule'lar secili gorunmesini engellemek icin tamamlandi.

Paket 8 canlı işlem davranışını değiştirmedi. Sadece Dashboard filtre/strateji seçim kalıcılığı ve Paper Lab aktivasyon görünürlüğünü stabilize etti.

## 2. Problem tanimi

Onceki dashboard checkbox mantigi `!selected.length` durumunda aktif item'lari secili gosterebiliyordu. Bu, backend explicit secim listesi bos oldugunda veya kaydetme hatasi sonrasi draft kayboldugunda kullaniciya tum secimler aktifmis gibi gorunebiliyordu.

Paper Lab kaydetme akisi da backend basarili response secimini frontend snapshot'i ile dogrulamadan draft'i temizliyordu.

## 3. Degisen dosyalar

- `frontend/js/pages/dashboard.js`
- `frontend/js/app/rules.js`
- `scripts/level1_40_13_rule_selection_persistence_audit.py`
- `docs/LEVEL1_40_13_RULE_SELECTION_PERSISTENCE_AUDIT.json`
- `docs/LEVEL1_40_13_RULE_SELECTION_PERSISTENCE_AUDIT.md`
- `docs/PACKAGE_08_RULE_SELECTION_PERSISTENCE.md`
- `README.md`
- `todo.md`

Backend route veya rule engine dosyalarina dokunulmadi.

## 4. Dashboard secim mantigi

Dashboard secimi artik `ids + explicit` modeliyle hesaplanir:

- Kullanici draft secimi varsa checkbox draft'a gore cizilir.
- Backend `selected_filter_ids` veya `selected_strategy_ids` listesi verdiyse liste bos bile olsa explicit backend secimi sayilir.
- Backend explicit liste vermediyse ilk acilista aktif rule'lar fallback olarak secili gorunur.

Kor all-active fallback `!selected.length` davranisindan cikarildi.

## 5. Paper Lab kaydetme dogrulamasi

`activatePaperLabRules()` artik:

- Kaydetme basinda filtre/strateji snapshot'i alir.
- Kaydetme sirasinda `dashboardRuleSelectionSaving` ile cift tiklamayi engeller.
- Backend response icindeki `selected_filter_ids` ve `selected_strategy_ids` listelerini gonderilen snapshot ile karsilastirir.
- Mismatch varsa draft'i korur ve kullaniciya hata logu yazar.
- Backend hata verirse draft'i korur ve checkboxlar kullanicinin son seciminde kalir.
- Backend basarili ve dogrulanmis response donerse draft'i temizler.
- Audit yazma hatasini ana save basarisizligi saymaz.

## 6. Backend davranisi degisti mi?

Hayir. Backend route, model kombinasyon hesabi, rule compatibility hesabi, strateji/filter karar motoru ve Paper Lab matematik davranisi degismedi.

## 7. Dokunulmayan kritik dosyalar

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
- Canli trade endpoint davranisi
- Binance, Futures, Karabasan, bot start/stop ve emir mantigi

## 8. Test sonuclari

- `py -X pycache_prefix=.pycache_paket8 -m py_compile backend\main.py webhook_server.py scripts\level1_40_07_frontend_api_inventory.py scripts\level1_40_08_api_contract_diff.py scripts\level1_40_09_missing_endpoint_report.py scripts\level1_40_10_mutating_endpoint_safety_audit.py scripts\level1_40_11_real_trade_manual_review_matrix.py scripts\level1_40_12_owner_approval_contract_audit.py scripts\level1_40_13_rule_selection_persistence_audit.py`: pass
- `py scripts\level1_40_06_api_route_inventory.py`: pass, `route_count=891`
- `py scripts\level1_40_07_frontend_api_inventory.py`: pass, `call_count=87`, `unique_base_path_count=72`
- `py scripts\level1_40_08_api_contract_diff.py --strict`: pass, `missing_path_count=0`, `method_mismatch_count=0`
- `py scripts\level1_40_09_missing_endpoint_report.py`: pass, `true_blocker_count=0`, `parser_gap_or_false_positive_count=0`
- `py scripts\level1_40_10_mutating_endpoint_safety_audit.py`: pass, `status=ok`, `mutating_call_count=50`, `unclassified_mutating_count=0`
- `py scripts\level1_40_11_real_trade_manual_review_matrix.py`: pass, `status=ok`, `critical_real_trade_count=13`, `unknown_real_trade_risk_type_count=0`
- `py scripts\level1_40_12_owner_approval_contract_audit.py`: pass, `status=ok`, `order_submission_contract_ok=true`
- `py scripts\level1_40_13_rule_selection_persistence_audit.py`: pass, `status=ok`, `dashboard_explicit_selection_guard=true`, `response_filter_selection_verified=true`, `response_strategy_selection_verified=true`, `draft_preserved_on_error=true`
- `node --check frontend\js\pages\dashboard.js`: calistirilamadi, Node PATH'te yok
- `node --check frontend\js\app\rules.js`: calistirilamadi, Node PATH'te yok

Manuel kabul testi:

1. Dashboard acilir.
2. Strateji / Filtre panelinde tum secimler gorunur.
3. Birkac filtre ve strateji kapatilir.
4. Kaydet'e basilir.
5. Backend basariliysa ayni secimler ekranda kalir.
6. Sayfa/sync sonrasi ayni secimler korunur.
7. Backend hata verirse checkboxlar kullanicinin son sectigi haliyle kalir.
8. Hata logunda Paper Lab kombinasyonu kaydedilemedi ve secim korundu mesaji gorunur.

## 9. Paket 9'a gecis karari

40.06-40.13 kalite zinciri temiz kaldigi, contract guard temiz oldugu ve 40.13 `status=ok` dondugu surece Paket 9'a gecis uygundur.
