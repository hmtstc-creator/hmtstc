#!/usr/bin/env python3
from __future__ import annotations
import os, subprocess, sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
os.environ.setdefault('HMTSTC_OFFLINE_QUALITY_CHECK','1')
if not (ROOT/'tests/api/test_real_readiness.py').exists():
    print('LEVEL1_40_16_REAL_READINESS_TESTS_FAIL: test file missing'); raise SystemExit(1)
result=subprocess.run([sys.executable,'-m','pytest','-q','tests/api/test_real_readiness.py'], cwd=ROOT, env=os.environ.copy())
if result.returncode:
    print('LEVEL1_40_16_REAL_READINESS_TESTS_FAIL: pytest failed'); raise SystemExit(result.returncode)
print('LEVEL1_40_16_REAL_READINESS_TESTS_OK')
