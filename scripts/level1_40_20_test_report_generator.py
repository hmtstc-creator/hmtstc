#!/usr/bin/env python3
from __future__ import annotations
import json, subprocess, sys
from datetime import datetime, timezone
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
DOCS=ROOT/'docs'; DOCS.mkdir(exist_ok=True)
commands=[
    ['python3','-m','compileall','-q','backend','scripts','tests'],
    ['python3','scripts/level1_40_05_runtime_leak_guard.py'],
    ['python3','scripts/level1_40_12_summary_regression_check.py'],
    [sys.executable,'-m','pytest','-q'],
]
results=[]
for cmd in commands:
    proc=subprocess.run(cmd, cwd=ROOT, text=True, capture_output=True)
    results.append({'cmd':' '.join(cmd),'returncode':proc.returncode,'stdout':proc.stdout[-4000:],'stderr':proc.stderr[-4000:]})
report={'status':'ok' if all(r['returncode']==0 for r in results) else 'blocked','generated_at':datetime.now(timezone.utc).isoformat(),'results':results}
(DOCS/'LEVEL1_40_20_TEST_REPORT.json').write_text(json.dumps(report,ensure_ascii=False,indent=2), encoding='utf-8')
md=['# Level1 40.20 — Test Report','',f"Status: **{report['status']}**",'']
for r in results:
    md.append(f"- `{r['cmd']}` → `{r['returncode']}`")
(DOCS/'LEVEL1_40_20_TEST_REPORT.md').write_text('\n'.join(md)+'\n', encoding='utf-8')
if report['status']!='ok':
    print('LEVEL1_40_20_TEST_REPORT_GENERATOR_FAIL'); raise SystemExit(1)
print('LEVEL1_40_20_TEST_REPORT_GENERATOR_OK')
