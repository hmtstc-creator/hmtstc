#!/usr/bin/env python3
from __future__ import annotations
import json, os, sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'backend'))
os.environ.setdefault('HMTSTC_OFFLINE_QUALITY_CHECK','1')
from main import app  # noqa: E402
paths=[
    '/api/quality/revision-34','/api/quality/revision-35','/api/quality/revision-36','/api/quality/revision-37','/api/summary',
]
registered={getattr(r,'path','') for r in app.routes}
missing=[p for p in paths if p not in registered]
route_map={getattr(r,'path',''): sorted(getattr(r,'methods',[])) for r in app.routes}
report={'status':'ok' if not missing else 'blocked','checked_paths':paths,'missing_paths':missing,'route_methods':{p:route_map.get(p) for p in paths}}
(ROOT/'docs'/'LEVEL1_40_21_QUALITY_PAYLOAD_CONTRACT.json').write_text(json.dumps(report,ensure_ascii=False,indent=2), encoding='utf-8')
(ROOT/'docs'/'LEVEL1_40_21_QUALITY_PAYLOAD_CONTRACT.md').write_text('# Level1 40.21 — Quality Payload Contract\n\nStatus: **%s**\n\nChecked paths: `%s`\n' % (report['status'], '`, `'.join(paths)), encoding='utf-8')
if missing:
    print('LEVEL1_40_21_QUALITY_PAYLOAD_CONTRACT_FAIL: '+','.join(missing)); raise SystemExit(1)
print('LEVEL1_40_21_QUALITY_PAYLOAD_CONTRACT_OK')
