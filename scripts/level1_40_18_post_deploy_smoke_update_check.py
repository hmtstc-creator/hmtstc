#!/usr/bin/env python3
from __future__ import annotations
import subprocess, sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
text=(ROOT/'scripts/post_deploy_check.py').read_text(encoding='utf-8')
if '/api/summary' not in text or 'summary_not_available' not in text:
    print('LEVEL1_40_18_POST_DEPLOY_SMOKE_UPDATE_FAIL: summary smoke missing'); raise SystemExit(1)
result=subprocess.run([sys.executable,'scripts/post_deploy_check.py','--offline'], cwd=ROOT)
if result.returncode:
    print('LEVEL1_40_18_POST_DEPLOY_SMOKE_UPDATE_FAIL: offline smoke failed'); raise SystemExit(result.returncode)
print('LEVEL1_40_18_POST_DEPLOY_SMOKE_UPDATE_OK')
