#!/usr/bin/env python3
from __future__ import annotations

import sys
from copy import deepcopy
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
sys.path.insert(0, str(BACKEND))

from core.config import DEFAULT_COIN_FILTER  # noqa: E402
import core.storage as storage_module  # noqa: E402
from core.storage import (  # noqa: E402
    build_persisted_scan_settings_contract,
    ensure_last_scan_settings_contract,
    normalize_settings,
    sync_settings_state,
)


def main() -> int:
    storage = (BACKEND / "core" / "storage.py").read_text(encoding="utf-8")
    routes = (BACKEND / "routes" / "settings_routes.py").read_text(encoding="utf-8")
    frontend = (ROOT / "frontend" / "js" / "app" / "settings.js").read_text(encoding="utf-8")

    normalized = normalize_settings({"coin_filter": None})
    canonical = normalize_settings({"coin_filter": {"min_quote_volume": 123456, "lightweight_score_min": 61}})
    shadow = {"settings": {"coin_filter": {"min_quote_volume": 1}}, "last_scan": {"status": "ok", "time": "2026-06-15T00:00:00"}}
    sync_settings_state(shadow, canonical)
    ensure_last_scan_settings_contract(shadow, canonical)
    snapshot = build_persisted_scan_settings_contract(canonical)
    original_snapshot = {"coin_filter": {"min_quote_volume": 77}, "coin_filter_effective": {"min_quote_volume": 77}, "bot": {}}
    completed_scan = {"last_scan": {"settings_snapshot": deepcopy(original_snapshot), "coin_filter_settings_used": {"min_quote_volume": 77}}}
    ensure_last_scan_settings_contract(completed_scan, canonical)
    written: dict = {}

    def capture_write(_path, payload):
        written.update(deepcopy(payload))

    with (
        patch.object(storage_module, "read_json_file", return_value={"users": {"default": {}}}),
        patch.object(storage_module, "write_json_file", side_effect=capture_write),
        patch.object(storage_module, "load_settings", return_value=deepcopy(canonical)),
    ):
        saved_shadow = storage_module.save_shadow(
            {
                "settings": {"coin_filter": {"min_quote_volume": 1}},
                "last_scan": {"status": "ok", "time": "2026-06-15T00:00:00"},
            },
            "audit-user",
        )

    checks = {
        "null_coin_filter_normalizes": isinstance(normalized.get("coin_filter"), dict) and normalized["coin_filter"] == DEFAULT_COIN_FILTER,
        "shadow_is_canonical_mirror": shadow["settings"] == canonical and shadow.get("settings_source") == "settings_store_mirror",
        "scan_has_settings_snapshot": shadow["last_scan"].get("settings_snapshot") == snapshot,
        "scan_has_coin_filter_settings_used": shadow["last_scan"].get("coin_filter_settings_used") == canonical["coin_filter"],
        "existing_scan_snapshot_is_preserved": completed_scan["last_scan"].get("settings_snapshot") == original_snapshot and completed_scan["last_scan"].get("coin_filter_settings_used") == {"min_quote_volume": 77},
        "save_shadow_forces_canonical_settings": "canonical_settings = load_settings(user_key)" in storage and "ensure_last_scan_settings_contract(normalized, canonical_settings)" in storage,
        "save_shadow_behavior_uses_settings_store": saved_shadow.get("settings") == canonical and written.get("users", {}).get("audit-user", {}).get("settings") == canonical,
        "save_shadow_behavior_persists_scan_contract": saved_shadow.get("last_scan", {}).get("settings_snapshot") == snapshot and saved_shadow.get("last_scan", {}).get("coin_filter_settings_used") == canonical["coin_filter"],
        "settings_write_response_declares_source": '"source": "settings_store"' in routes,
        "save_does_not_start_scan": "scan_market(" not in routes and "coinfilter-test-scan" not in routes,
        "frontend_preserves_quality_score": "quality_score_min" in frontend,
        "frontend_preserves_lightweight_score": "lightweight_score_min" in frontend,
    }
    failed = [name for name, passed in checks.items() if not passed]
    if failed:
        print("LEVEL1_40_42_PACKAGE_22_COINFILTER_SETTINGS_CONTRACT_AUDIT_FAIL")
        print("failed=" + ",".join(failed))
        return 1

    print("LEVEL1_40_42_PACKAGE_22_COINFILTER_SETTINGS_CONTRACT_AUDIT_OK")
    print("status=ok")
    print(f"checks={len(checks)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
