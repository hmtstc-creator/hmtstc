# Paket 10.20 Last Scan Contract Preservation

## 1. Paket amaci

Paket 10.20, CoinFilter test scan sonucunun `normalize_shadow_state` sirasinda daraltilmasini engeller.

Test scan sonucu, runtime `last_scan`, `scan_history`, `/api/bot/last-scan` ve frontend boyunca ayni pipeline contract'ini korur.

## 2. Korunan last_scan alanlari

Storage normalizasyonu artik su alanlari korur:

- `mode`
- `test_scan`
- `eligible_universe_count`
- `universe_total_seen`
- `universe_rejected_count`
- `universe_rejection_breakdown`
- `pipeline`

Mevcut candidate, row, diagnostics ve trace alanlari korunmaya devam eder.

## 3. Runtime repair

Eski runtime store'da `last_scan.pipeline` eksik, fakat son `scan_history` kaydinda pipeline mevcut olabilir.

Repair sadece su kosullarda calisir:

- `last_scan.pipeline` yoktur.
- Son history kaydi pipeline icerir.
- History zamani `last_scan` ile ayni veya daha yenidir.

Mevcut pipeline varsa history daha yeni olsa bile overwrite edilmez.

## 4. API response

`/api/bot/last-scan` artik acik olarak sunlari doner:

- `test_scan`
- `pipeline`
- `scan_mode`
- Universe sayilari ve rejection breakdown

## 5. Yeni audit

- `scripts/level1_40_35_last_scan_contract_preservation_audit.py`
- `docs/LEVEL1_40_35_LAST_SCAN_CONTRACT_PRESERVATION_AUDIT.json`
- `docs/LEVEL1_40_35_LAST_SCAN_CONTRACT_PRESERVATION_AUDIT.md`

Audit statik contract kontrollerine ek olarak eski store repair ve mevcut pipeline overwrite korumasini runtime probe ile dogrular.

## 6. Degisen dosyalar

- `backend/core/storage.py`
- `backend/routes/bot_routes.py`
- `scripts/level1_40_35_last_scan_contract_preservation_audit.py`
- `docs/LEVEL1_40_35_LAST_SCAN_CONTRACT_PRESERVATION_AUDIT.json`
- `docs/LEVEL1_40_35_LAST_SCAN_CONTRACT_PRESERVATION_AUDIT.md`
- `docs/PACKAGE_10_20_LAST_SCAN_CONTRACT_PRESERVATION.md`
- `README.md`
- `todo.md`

## 7. Test sonuclari

- `py -X pycache_prefix=.pycache_paket10_20 -m py_compile backend\core\storage.py backend\routes\bot_routes.py scripts\level1_40_35_last_scan_contract_preservation_audit.py`: pass
- `py -c "import sys; sys.path.insert(0, 'backend'); import main; print('backend import ok')"`: pass, `backend import ok`
- `py scripts\level1_40_35_last_scan_contract_preservation_audit.py`: pass, `status=ok`, `normalize_last_scan_preserves_pipeline=true`, `runtime_repair_restores_contract=true`, `last_scan_payload_returns_pipeline=true`, `previous_40_20_to_40_34_status_ok=true`
- 40.35 runtime repair probe: pass, `test_scan=true`, `mode=coinfilter_test_scan`, `universe_total_seen=120`, pipeline mevcut
- 40.35 existing contract probe: pass, mevcut pipeline ve normal bot mode history tarafindan overwrite edilmedi
- `py scripts\level1_40_34_coinfilter_test_scan_timeout_audit.py`: pass, `status=ok`
- `py scripts\level1_40_33_coinfilter_final_pipeline_audit.py`: pass, `status=ok`
- `py scripts\level1_40_32_bot_restore_first_tick_audit.py`: pass, `status=ok`
- `py scripts\level1_40_31_bot_restore_real_loop_audit.py`: pass, `status=ok`
- `py scripts\level1_40_30_bot_runtime_heartbeat_truth_audit.py`: pass, `status=ok`
- `py scripts\level1_40_29_coinfilter_persistence_and_8h_report_audit.py`: pass, `status=ok`
- `py scripts\level1_40_09_missing_endpoint_report.py`: pass, `missing_path_count=0`, `method_mismatch_count=0`, `true_blocker_count=0`, `parser_gap_or_false_positive_count=0`
- `py scripts\level1_40_08_api_contract_diff.py --strict`: pass, `matched_call_count=94`, `missing_path_count=0`, `method_mismatch_count=0`

Canli runtime store repair ve test scan/last-scan birebir response karsilastirmasi deploy sonrasi kabul adiminda yapilmalidir.

## 8. Canli kabul

Deploy ve restart sonrasi CoinFilter test scan ve `/api/bot/last-scan` response'lari karsilastirilir.

Beklenen:

- `scanned` degerleri ayni.
- `test_scan=true`.
- `scan_mode=coinfilter_test_scan`.
- `pipeline` mevcut.
- `pipeline.market_universe.total_seen` dolu.
- `pipeline.coinfilter.passed` dolu.
- Dashboard ve CoinFilter Ctrl+F5 sonrasi ayni scan degerlerini gosterir.

## 9. Paket 11'e gecis karari

Paket 11'e sadece 40.20-40.35 audit zinciri `ok` olduktan ve canli test scan/last-scan contract degerleri birebir dogrulandiktan sonra gecilebilir.
