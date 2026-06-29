#!/usr/bin/env python3
from __future__ import annotations
import hashlib, json, subprocess, zipfile
from datetime import datetime, timezone
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
out=ROOT.parent/'hmtstc_revizyon_40_quality_foundation_full_project.zip'
# Run final quality before package.
proc=subprocess.run(['python3','scripts/level1_40_23_final_quality.py'], cwd=ROOT)
if proc.returncode: print('LEVEL1_40_24_FINAL_PACKAGE_FAIL: final quality failed'); raise SystemExit(proc.returncode)
for path in [ROOT/'backend/settings_store.json',ROOT/'backend/shadow_store.json',ROOT/'backend/auth_store.json',ROOT/'backend/rule_store.json',ROOT/'backend/audit_store.json',ROOT/'backend/real_trade_store.json',ROOT/'backend/.env']:
    if path.exists() and path.is_file(): path.unlink()
if (ROOT/'backend/runtime_backups').exists():
    import shutil; shutil.rmtree(ROOT/'backend/runtime_backups')
exclude={'backend/.env','backend/settings_store.json','backend/shadow_store.json','backend/auth_store.json','backend/rule_store.json','backend/audit_store.json','backend/real_trade_store.json'}
with zipfile.ZipFile(out,'w',zipfile.ZIP_DEFLATED) as z:
    for p in sorted(ROOT.rglob('*')):
        if p.is_dir(): continue
        rel=p.relative_to(ROOT).as_posix()
        if rel in exclude or rel.startswith('backend/runtime_backups/') or rel.endswith('.pyc') or '/__pycache__/' in rel or rel.startswith('.pytest_cache/'):
            continue
        z.write(p, rel)
digest=hashlib.sha256(out.read_bytes()).hexdigest()
manifest={'status':'ok','zip':out.name,'sha256':digest,'generated_at':datetime.now(timezone.utc).isoformat(),'file_count':len(zipfile.ZipFile(out).namelist())}
(ROOT/'docs'/'LEVEL1_40_24_FINAL_PACKAGE_MANIFEST.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2), encoding='utf-8')
print('LEVEL1_40_24_FINAL_PACKAGE_OK')
print(json.dumps(manifest,ensure_ascii=False,indent=2))
