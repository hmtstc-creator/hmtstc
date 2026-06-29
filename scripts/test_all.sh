#!/usr/bin/env bash
set -euo pipefail
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"
export HMTSTC_OFFLINE_QUALITY_CHECK="${HMTSTC_OFFLINE_QUALITY_CHECK:-1}"
rm -f backend/settings_store.json backend/shadow_store.json backend/auth_store.json backend/rule_store.json backend/audit_store.json backend/real_trade_store.json
rm -rf backend/runtime_backups
python3 -m compileall -q backend scripts tests
find frontend/js -name '*.js' -print0 | xargs -0 -I{} node --check {}
python3 scripts/level1_40_05_runtime_leak_guard.py
python3 scripts/level1_40_11_recent_gates_audit.py
python3 scripts/level1_40_12_summary_regression_check.py
python3 scripts/level1_40_13_settings_unit_tests_check.py
python3 scripts/level1_40_14_rule_schema_tests_check.py
python3 scripts/level1_40_15_audit_schema_tests_check.py
python3 scripts/level1_40_16_real_readiness_tests_check.py
python3 scripts/level1_40_17_real_lock_regression_check.py
python3 scripts/level1_40_18_post_deploy_smoke_update_check.py
python3 scripts/level1_41_real_order_safety_final_quality.py
pytest -q
rm -f backend/settings_store.json backend/shadow_store.json backend/auth_store.json backend/rule_store.json backend/audit_store.json backend/real_trade_store.json
rm -rf backend/runtime_backups
python3 scripts/level1_40_05_runtime_leak_guard.py
printf '%s\n' 'LEVEL1_TEST_ALL_OK'
