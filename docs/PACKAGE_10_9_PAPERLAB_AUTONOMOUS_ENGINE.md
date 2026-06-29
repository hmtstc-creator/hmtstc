# Paket 10.9 Paper Lab Autonomous Research Engine

## 1. Paket amaci

Paket 10.9, Paper Lab'i Dashboard active selection'dan tamamen ayri ve tekrar tekrar calisabilen bagimsiz arastirma laboratuvari olarak sabitler.

Korunan urun karari:

- Dashboard secimleri canli botun kullanacagi filtre/strateji secimidir.
- Paper Lab Dashboard secimlerine bakarak kapsam daraltmaz.
- Paper Lab tum enabled filtre ve tum enabled strateji kombinasyonlarini arastirir.
- Paper Lab calismasi Dashboard `selected_filter_ids`, `selected_strategy_ids` ve `lastKnownRulesSelection` alanlarini degistirmez.

Rollback yapilmadi. Paket 10.5, 10.6, 10.7 ve 10.8 davranislari korundu.

## 2. Paper Lab kaynak verisi

Backend Paper Lab model uretimi `build_custom_models(username)` varsayilaniyla `get_enabled_rules(username)` kaynagini kullanir.

Paper Lab sunlari kullanir:

- Tum enabled filtreler
- Tum enabled stratejiler
- `paper_lab_filter_ids`
- `paper_lab_strategy_ids`

Paper Lab sunlari kullanmaz:

- Dashboard `selected_filter_ids`
- Dashboard `selected_strategy_ids`

## 3. Runtime lifecycle

Frontend Paper Lab state alani genisletildi:

- `paperLabEngineStatus`: `idle`, `running`, `completed`, `failed`
- `paperLabRunning`
- `paperLabRunId`
- `paperLabCandidateCount`
- `paperLabModelCount`
- `paperLabAccepted`
- `paperLabRejected`
- `paperLabStartedAt`
- `paperLabCompletedAt`
- `paperLabRun`
- `lastPaperLabResult`

`activatePaperLabRules` her calismada yeni run baslatabilir. Sadece halihazirda calisan run varken ikinci tiklama guardlanir. `finally` icinde `paperLabRunning=false` yazilir.

## 4. Sonuc havuzu

Paper Lab sonucu Dashboard rules objesine yazilmaz. Sonuc havuzu ayri tutulur:

- `HMTSTC_DATA.paperLabStatus`
- `HMTSTC_APP.state.lastPaperLabResult`
- `HMTSTC_APP.state.paperLabRun`

Response metrikleri:

- `run_id`
- `paper_lab_candidate_count`
- `accepted_combinations`
- `rejected_combinations`
- `model_count`
- `completed_at`

## 5. Yeni audit

Yeni kalite kapisi:

- `scripts/level1_40_24_paperlab_autonomous_engine_audit.py`
- `docs/LEVEL1_40_24_PAPERLAB_AUTONOMOUS_ENGINE_AUDIT.json`
- `docs/LEVEL1_40_24_PAPERLAB_AUTONOMOUS_ENGINE_AUDIT.md`

40.24 audit su alanlari blocker yapar:

- `paper_lab_not_using_selected_filter_ids`
- `paper_lab_not_using_selected_strategy_ids`
- `dashboard_selection_not_modified_by_paper_lab`
- `paper_lab_running_finally_reset`
- `paper_lab_repeatable_runs_supported`
- `paper_lab_state_isolated`
- 40.20, 40.21, 40.22 ve 40.23 status `ok`

## 6. Degisen dosyalar

- `backend/services/rule_engine.py`
- `frontend/js/app/rules.js`
- `frontend/js/app/state.js`
- `scripts/level1_40_24_paperlab_autonomous_engine_audit.py`
- `docs/LEVEL1_40_24_PAPERLAB_AUTONOMOUS_ENGINE_AUDIT.json`
- `docs/LEVEL1_40_24_PAPERLAB_AUTONOMOUS_ENGINE_AUDIT.md`
- `docs/PACKAGE_10_9_PAPERLAB_AUTONOMOUS_ENGINE.md`
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

- `py -X pycache_prefix=.pycache_paket10_9 -m py_compile backend\main.py backend\routes\rule_routes.py backend\services\rule_engine.py scripts\level1_40_24_paperlab_autonomous_engine_audit.py`: pass
- `py scripts\level1_40_20_live_startup_rules_hydration_audit.py`: pass, `status=ok`
- `py scripts\level1_40_21_auth_restore_truth_audit.py`: pass, `status=ok`
- `py scripts\level1_40_22_coinfilter_rules_paperlab_audit.py`: pass, `status=ok`
- `py scripts\level1_40_23_rules_paperlab_independence_audit.py`: pass, `status=ok`
- `py scripts\level1_40_24_paperlab_autonomous_engine_audit.py`: pass, `status=ok`, `paper_lab_not_using_selected_filter_ids=true`, `paper_lab_not_using_selected_strategy_ids=true`, `paper_lab_repeatable_runs_supported=true`
- `py scripts\level1_40_07_frontend_api_inventory.py`: pass, `call_count=93`, `unique_base_path_count=73`
- `py scripts\level1_40_08_api_contract_diff.py --strict`: pass, `matched_call_count=93`, `missing_path_count=0`, `method_mismatch_count=0`
- `py scripts\level1_40_09_missing_endpoint_report.py`: pass, `missing_path_count=0`, `method_mismatch_count=0`, `true_blocker_count=0`
- `py scripts\level1_40_10_mutating_endpoint_safety_audit.py`: pass, `mutating_call_count=51`, `unclassified_mutating_count=0`
- `node --check frontend\js\app\rules.js`: calistirilamadi, Node PATH'te yok

## 9. Canli kabul testi

1. Dashboard'da 2 filtre / 2 strateji secilir.
2. Dashboard secimi kaydedilir.
3. Paper Lab calistirilir.
4. Paper Lab tum enabled filtre/strateji kapsaminda kombinasyon uretir.
5. Paper Lab bitince tekrar calistirilir.
6. Yeni run baslar, stuck/loading kalmaz.
7. Dashboard'a donuldugunde 2 filtre / 2 strateji halen secilidir.

## 10. Paket 11'e gecis karari

Paket 11'e sadece 40.20, 40.21, 40.22, 40.23 ve 40.24 auditleri `ok` olduktan ve canli kabul testleri basarili tamamlandiktan sonra gecilebilir.
