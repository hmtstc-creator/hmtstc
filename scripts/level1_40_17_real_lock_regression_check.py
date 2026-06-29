#!/usr/bin/env python3
from __future__ import annotations
import os, subprocess, sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
os.environ.setdefault('REAL_TRADING_ENABLED','false')
os.environ.setdefault('REAL_TRADING_DRY_RUN','true')
result=subprocess.run([sys.executable,'-m','pytest','-q','tests/unit/test_real_lock_regression.py'], cwd=ROOT, env=os.environ.copy())
if result.returncode:
    print('LEVEL1_40_17_REAL_LOCK_REGRESSION_FAIL: pytest failed'); raise SystemExit(result.returncode)
print('LEVEL1_40_17_REAL_LOCK_REGRESSION_OK')
