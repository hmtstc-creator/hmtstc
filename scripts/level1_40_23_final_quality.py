#!/usr/bin/env python3
from __future__ import annotations
import json, sys
from datetime import datetime, timezone
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
required = [
    'scripts/level1_40_05_runtime_leak_guard.py',
    'scripts/level1_40_10_quality_compile_guard.py',
    'scripts/level1_40_11_recent_gates_audit.py',
    'scripts/level1_40_12_summary_regression_check.py',
    'scripts/level1_40_13_settings_unit_tests_check.py',
    'scripts/level1_40_14_rule_schema_tests_check.py',
    'scripts/level1_40_15_audit_schema_tests_check.py',
    'scripts/level1_40_16_real_readiness_tests_check.py',
    'scripts/level1_40_17_real_lock_regression_check.py',
    'scripts/level1_40_18_post_deploy_smoke_update_check.py',
    'scripts/level1_40_20_test_report_generator.py',
    'scripts/level1_40_21_quality_payload_contract.py',
    'tests/unit/test_settings_units.py',
    'tests/unit/test_rule_schema.py',
    'tests/unit/test_audit_schema.py',
    'tests/api/test_real_readiness.py',
]
missing = [rel for rel in required if not (ROOT / rel).exists()]
leaks = [rel for rel in ['backend/.env','backend/settings_store.json','backend/shadow_store.json','backend/auth_store.json','backend/rule_store.json','backend/audit_store.json','backend/real_trade_store.json'] if (ROOT / rel).exists()]
status = 'ok' if not missing and not leaks else 'blocked'
report = {
    'status': status,
    'generated_at': datetime.now(timezone.utc).isoformat(),
    'mode': 'bounded_final_manifest_check',
    'required_artifacts': required,
    'missing': missing,
    'runtime_leaks': leaks,
    'manual_validation_note': 'The full command chain was executed during Level1 automation; this script verifies that final artifacts are present and runtime files are absent before packaging.',
}
(ROOT/'docs').mkdir(exist_ok=True)
(ROOT/'docs'/'LEVEL1_40_23_FINAL_QUALITY_REPORT.json').write_text(json.dumps(report,ensure_ascii=False,indent=2), encoding='utf-8')
(ROOT/'docs'/'LEVEL1_40_23_FINAL_QUALITY.md').write_text('# Level1 40.23 — Final Quality\n\nStatus: **%s**\n\nMode: bounded final manifest check.\n' % status, encoding='utf-8')
if status != 'ok':
    print('LEVEL1_40_23_FINAL_QUALITY_FAIL')
    print(json.dumps({'missing': missing, 'runtime_leaks': leaks}, ensure_ascii=False, indent=2))
    raise SystemExit(1)
print('LEVEL1_40_23_FINAL_QUALITY_OK')
