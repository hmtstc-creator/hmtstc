import py_compile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REQUIRED = [
    ROOT / 'backend/services/replay_explainability_service.py',
    ROOT / 'backend/services/revision_33_service.py',
    ROOT / 'backend/routes/model_routes.py',
    ROOT / 'backend/routes/quality_routes.py',
    ROOT / 'frontend/js/pages/reports.js',
    ROOT / 'frontend/js/pages/intelligence.js',
]

for path in REQUIRED:
    if not path.exists():
        raise SystemExit(f'MISSING: {path.relative_to(ROOT)}')

for path in (ROOT / 'backend').rglob('*.py'):
    py_compile.compile(str(path), doraise=True)

quality = (ROOT / 'backend/routes/quality_routes.py').read_text(encoding='utf-8')
model = (ROOT / 'backend/routes/model_routes.py').read_text(encoding='utf-8')
api = (ROOT / 'frontend/js/app/api.js').read_text(encoding='utf-8')
reports = (ROOT / 'frontend/js/pages/reports.js').read_text(encoding='utf-8')
intel = (ROOT / 'frontend/js/pages/intelligence.js').read_text(encoding='utf-8')
checks = {
    'revision_33_quality_routes': '/revision-33' in quality and 'revision-33/evidence-chain' in quality,
    'model_replay_endpoints': '/replay-index' in model and '/evidence-chain' in model and '/trade-explain' in model,
    'api_sync': 'revision33Quality' in api and 'reportsReplayFinal' in api,
    'reports_ui': 'Rev33 Trade Explainability' in reports and 'Rev33 Evidence Chain' in reports,
    'intelligence_ui': 'Rev33 Reports & Replay' in intel,
    'read_only_policy': 'no_real_order_side_effect' in (ROOT / 'backend/services/replay_explainability_service.py').read_text(encoding='utf-8'),
}
failed = [name for name, ok in checks.items() if not ok]
if failed:
    raise SystemExit('FAILED: ' + ', '.join(failed))
print('REVISION_33_QUALITY_OK')
