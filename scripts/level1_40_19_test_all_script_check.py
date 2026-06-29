#!/usr/bin/env python3
from __future__ import annotations
import subprocess
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
script=ROOT/'scripts/test_all.sh'
if not script.exists(): print('LEVEL1_40_19_TEST_ALL_SCRIPT_FAIL: missing'); raise SystemExit(1)
result=subprocess.run(['bash','scripts/test_all.sh'], cwd=ROOT)
if result.returncode:
    print('LEVEL1_40_19_TEST_ALL_SCRIPT_FAIL: test_all failed'); raise SystemExit(result.returncode)
print('LEVEL1_40_19_TEST_ALL_SCRIPT_OK')
