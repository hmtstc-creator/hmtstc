from __future__ import annotations

import importlib
import pathlib
import py_compile
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
BACKEND = ROOT / 'backend'
FRONTEND = ROOT / 'frontend'

sys.path.insert(0, str(BACKEND))


def assert_true(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def main() -> None:
    for path in BACKEND.rglob('*.py'):
        if any(part in {'__pycache__', '.venv', 'venv'} for part in path.parts):
            continue
        py_compile.compile(str(path), doraise=True)

    main = importlib.import_module('main')
    routes = {route.path for route in main.app.routes}
    required_routes = {
        '/api/real/emergency/recovery',
        '/api/real/emergency/checklist',
        '/api/real/emergency/lock',
        '/api/real/emergency/recovery-unlock',
        '/api/real/emergency/close-preview',
        '/api/quality/revision-23',
        '/api/quality/revision-23/emergency-recovery',
        '/api/quality/revision-23/emergency-close',
        '/api/quality/revision-23/disaster-recovery',
        '/api/quality/revision-23/audit-timeline',
    }
    missing = sorted(required_routes - routes)
    assert_true(not missing, f'Missing Rev23 routes: {missing}')

    from services.emergency_recovery_service import build_emergency_recovery_status, build_emergency_close_preview_v2, trigger_emergency_lock
    from services.revision_23_service import build_revision_23_quality_report

    data = {}
    trigger_emergency_lock(data, user='test', reason='quality_check')
    status = build_emergency_recovery_status(data, {})
    assert_true(status.get('lock_active') is True, 'Emergency lock should be active after trigger.')
    preview = build_emergency_close_preview_v2(data, {})
    assert_true((preview.get('policy') or {}).get('auto_close') is False, 'Emergency close must be preview-only.')
    report = build_revision_23_quality_report(data, {})
    assert_true(report.get('revision') == 23, 'Revision 23 quality report mismatch.')

    forbidden = ['backend/.env', 'backend/auth_store.json', 'backend/settings_store.json', 'backend/shadow_store.json', 'backend/runtime_backups']
    for rel in forbidden:
        assert_true(not (ROOT / rel).exists(), f'Runtime file leaked: {rel}')

    for path in (FRONTEND / 'js').rglob('*.js'):
        text = path.read_text(encoding='utf-8')
        assert_true(text.count('{') >= text.count('}') - 10, f'Potential JS brace issue: {path}')

    print('REVISION_23_QUALITY_OK')


if __name__ == '__main__':
    main()
