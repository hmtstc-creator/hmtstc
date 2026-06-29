#!/usr/bin/env python3
from __future__ import annotations
import subprocess, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
required = ROOT / 'tests' / 'unit' / 'test_settings_units.py'
if not required.exists():
    print('LEVEL1_40_13_SETTINGS_UNIT_TESTS_FAIL: test file missing'); raise SystemExit(1)
result = subprocess.run([sys.executable, '-m', 'pytest', '-q', 'tests/unit/test_settings_units.py'], cwd=ROOT)
if result.returncode != 0:
    print('LEVEL1_40_13_SETTINGS_UNIT_TESTS_FAIL: pytest failed'); raise SystemExit(result.returncode)
print('LEVEL1_40_13_SETTINGS_UNIT_TESTS_OK')
