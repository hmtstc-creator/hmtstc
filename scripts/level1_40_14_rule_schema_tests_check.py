#!/usr/bin/env python3
from __future__ import annotations
import subprocess, sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
if not (ROOT/'tests/unit/test_rule_schema.py').exists():
    print('LEVEL1_40_14_RULE_SCHEMA_TESTS_FAIL: test file missing'); raise SystemExit(1)
result=subprocess.run([sys.executable,'-m','pytest','-q','tests/unit/test_rule_schema.py'], cwd=ROOT)
if result.returncode:
    print('LEVEL1_40_14_RULE_SCHEMA_TESTS_FAIL: pytest failed'); raise SystemExit(result.returncode)
print('LEVEL1_40_14_RULE_SCHEMA_TESTS_OK')
