# Paket 10.8 Rules Selection Persistence / Paper Lab Independence

## 1. Paket amaci

Paket 10.8, Dashboard active filtre/strateji secimini Paper Lab laboratuvar calismasindan ayirir.

Urun karari:

- Dashboard secimleri canli botun kullanacagi active filtre/strateji secimidir.
- Paper Lab bagimsiz laboratuvar alanidir.
- Paper Lab Dashboard secimini degistirmez.
- Paper Lab Dashboard secimiyle sinirlanmadan tum eligible filtre/strateji kombinasyonlarini calistirabilir.

Rollback yapilmadi. Paket 10.5, 10.6 ve 10.7 guardlari korundu. Binance, Futures, real-trade, order executor, Karabasan matematigi ve strategy/filter karar mantigi degismedi.

## 2. Dashboard active selection

Dashboard `Kaydet` butonu artik Paper Lab aktivasyonu yapmaz.

Yeni akış:

1. Dashboard checkbox state okunur.
2. `/api/rules/selection` endpointine `selected_filter_ids` ve `selected_strategy_ids` yazilir.
3. Backend ayni alanlari rule store active selection olarak persist eder.
4. Core refresh sonrasi ayni ID seti beklenir.
5. Render checked state sadece active selection ID setinden gelir.

Empty selected list ve missing selected field tumu secili anlamina gelmez.

## 3. Paper Lab independence

`/api/rules/activate-paper-lab` artik Dashboard active selection yazmaz.

Frontend:

- Paper Lab payload icinde Dashboard `selected_filter_ids` / `selected_strategy_ids` gondermez.
- Paper Lab response Dashboard `HMTSTC_DATA.rules.selected_*` alanlarina uygulanmaz.
- `lastKnownRulesSelection` Paper Lab tarafindan overwrite edilmez.
- Paper Lab sonucu `paperLabStatus`, `lastPaperLabResult` ve `paperLabRun` alanlarinda tutulur.
- `paperLabRunning` flag'i `finally` icinde resetlenir.

Backend:

- `activate_paper_lab_rules` active selection persist etmez.
- Paper Lab modeli `build_custom_models(..., use_active_selection=False)` varsayilanıyla tum enabled filtre/strateji setinden uretilir.
- Response `paper_lab_filter_ids`, `paper_lab_strategy_ids`, `paper_lab_candidate_count`, `run_id` ve kombinasyon metriklerini doner.

## 4. Runtime proof

Dashboard save proof state su zinciri token/secret icermeden tutar:

- `beforeSaveFilterIds` / `beforeSaveStrategyIds`
- `payloadFilterIds` / `payloadStrategyIds`
- `responseFilterIds` / `responseStrategyIds`
- `refreshFilterIds` / `refreshStrategyIds`
- `renderFilterIds` / `renderStrategyIds`
- `afterPaperLabFilterIds` / `afterPaperLabStrategyIds`
- `mismatch` / `mismatchStage`

Paper Lab sonrasi Dashboard selection degisirse proof `mismatch=true` yazar.

## 5. Yeni audit

Yeni kalite kapisi:

- `scripts/level1_40_23_rules_paperlab_independence_audit.py`
- `docs/LEVEL1_40_23_RULES_PAPERLAB_INDEPENDENCE_AUDIT.json`
- `docs/LEVEL1_40_23_RULES_PAPERLAB_INDEPENDENCE_AUDIT.md`

40.23 audit su alanlari blocker yapar:

- Dashboard active selection source of truth
- Empty/missing selected list default-all olmamasi
- Paper Lab'in `lastKnownRulesSelection` overwrite etmemesi
- Save response / refresh / render comparison proof
- Paper Lab payload'in Dashboard selected ids'e bagli olmamasi
- Paper Lab response'un Dashboard selected ids'e uygulanmamasi
- Paper Lab state'in ayri tutulmasi
- Paper Lab rerun guard ve `finally` reset
- Backend Paper Lab'in active selection persist etmemesi
- Backend Paper Lab'in tum enabled rules uzerinden calismasi
- 40.20, 40.21 ve 40.22 status `ok`

## 6. Degisen dosyalar

- `backend/routes/rule_routes.py`
- `backend/services/rule_engine.py`
- `frontend/js/app/rules.js`
- `frontend/js/app/state.js`
- `frontend/js/pages/dashboard.js`
- `scripts/level1_40_22_coinfilter_rules_paperlab_audit.py`
- `scripts/level1_40_23_rules_paperlab_independence_audit.py`
- `docs/LEVEL1_40_22_COINFILTER_RULES_PAPERLAB_AUDIT.json`
- `docs/LEVEL1_40_22_COINFILTER_RULES_PAPERLAB_AUDIT.md`
- `docs/LEVEL1_40_23_RULES_PAPERLAB_INDEPENDENCE_AUDIT.json`
- `docs/LEVEL1_40_23_RULES_PAPERLAB_INDEPENDENCE_AUDIT.md`
- `docs/PACKAGE_10_8_RULES_SELECTION_PAPERLAB_INDEPENDENCE.md`
- `README.md`
- `todo.md`

## 7. Dokunulmayan kritik dosyalar

- `backend/auth_store.json`
- `backend/settings_store.json`
- `backend/binance_credentials_store.json`
- `backend/shadow_store.json`
- `backend/services/*order*`
- `backend/services/*executor*`
- `backend/services/*binance*`
- `frontend/js/app/realTrade.js`
- `frontend/js/app/realApproval.js`
- `webhook_server.py`
- `deploy/*`

## 8. Test sonuclari

- `py -X pycache_prefix=.pycache_paket10_8 -m py_compile backend\main.py backend\routes\rule_routes.py backend\services\rule_engine.py scripts\level1_40_22_coinfilter_rules_paperlab_audit.py scripts\level1_40_23_rules_paperlab_independence_audit.py`: pass
- `py scripts\level1_40_20_live_startup_rules_hydration_audit.py`: pass, `status=ok`
- `py scripts\level1_40_21_auth_restore_truth_audit.py`: pass, `status=ok`
- `py scripts\level1_40_22_coinfilter_rules_paperlab_audit.py`: pass, `status=ok`
- `py scripts\level1_40_23_rules_paperlab_independence_audit.py`: pass, `status=ok`
- `py scripts\level1_40_07_frontend_api_inventory.py`: pass, `call_count=93`, `unique_base_path_count=73`
- `py scripts\level1_40_08_api_contract_diff.py --strict`: pass, `matched_call_count=93`, `missing_path_count=0`, `method_mismatch_count=0`
- `py scripts\level1_40_09_missing_endpoint_report.py`: pass, `missing_path_count=0`, `method_mismatch_count=0`, `true_blocker_count=0`
- `py scripts\level1_40_10_mutating_endpoint_safety_audit.py`: pass, `mutating_call_count=51`, `unclassified_mutating_count=0`
- `node --check frontend\js\app\rules.js`: calistirilamadi, Node PATH'te yok
- `node --check frontend\js\pages\dashboard.js`: calistirilamadi, Node PATH'te yok
- `node --check frontend\js\pages\strategies.js`: calistirilamadi, Node PATH'te yok
- `node --check frontend\js\app\api.js`: calistirilamadi, Node PATH'te yok

## 9. Canli kabul testi

### Dashboard Selection Persistence

1. Dashboard acilir.
2. Sadece 2 filtre ve 2 strateji secilir.
3. `Kaydet` tiklanir.
4. `2 filtre / 2 strateji kaydedildi` benzeri log gorulur.
5. Ctrl+F5 yapilir.
6. Sadece ayni 2 filtre / 2 strateji secili kalir.
7. Sayfa degistirilip Dashboard'a donulur.
8. Secimler korunur.

### Paper Lab Independence

1. Dashboard'da 2 filtre / 2 strateji secili kalir.
2. Paper Lab calistirilir.
3. Dashboard'a donulur.
4. Secimler halen ayni 2 filtre / 2 strateji olmalidir.
5. Paper Lab kendi eligible kapsaminda kombinasyon uretir.
6. Paper Lab sonucu Dashboard secimlerini degistirmez.

### Paper Lab Rerun

1. Paper Lab calistirilir.
2. Bitti veya hata verdi fark etmeksizin buton tekrar aktif olur.
3. Tekrar calistirilir.
4. Ikinci calistirmada stuck/loading kalmaz.
5. Hata varsa backend mesaji acik gorunur.
6. Dashboard secimi degismez.

## 10. Paket 11'e gecis karari

Paket 11'e sadece 40.20, 40.21, 40.22 ve 40.23 auditleri `ok`, Dashboard selection persistence testi, Paper Lab independence testi ve Paper Lab rerun testi basarili olduktan sonra gecilebilir.
