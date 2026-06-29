from pathlib import Path
import json

ROOT = Path(__file__).resolve().parents[1]

checks = {}

def read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")

storage = read("backend/core/storage.py")
config = read("backend/core/config.py")
analysis = read("backend/services/analysis_service.py")
universe = read("backend/services/coin_universe_service.py")
bot_routes = read("backend/routes/bot_routes.py")
dashboard_routes = read("backend/routes/dashboard_routes.py")

checks["shadow_default_has_settings_mirror"] = '"settings": {}' in config and '"settings_updated_at": None' in config
checks["storage_has_sync_settings_state"] = "def sync_settings_state" in storage and 'data["settings"] = normalized_settings' in storage
checks["save_settings_updates_shadow_snapshot"] = "save_shadow_settings_snapshot(user_key" in storage and "write_json_file(SETTINGS_FILE, container)" in storage
checks["shadow_normalization_preserves_settings"] = 'normalized["settings"] = normalize_settings(settings_snapshot)' in storage
checks["scan_market_records_settings_snapshot"] = '"settings_snapshot": settings_snapshot' in analysis and '"coin_filter_settings_used": coin_filter_settings_used' in analysis
checks["last_scan_normalization_keeps_settings_contract"] = '"settings_snapshot": last_scan.get("settings_snapshot"' in storage and '"coin_filter_settings_used": last_scan.get("coin_filter_settings_used"' in storage
checks["last_scan_endpoint_exposes_current_and_scan_settings"] = '"current_settings_snapshot": current_settings_snapshot' in bot_routes and '"settings_changed_since_scan": settings_changed_since_scan' in bot_routes
checks["dashboard_bundle_exposes_current_and_scan_settings"] = '"current_settings_snapshot": current_settings_snapshot' in dashboard_routes and 'build_cached_last_scan_payload(user, data, settings)' in dashboard_routes
checks["dashboard_and_last_scan_sync_shadow_settings"] = "if sync_settings_state(data, settings):" in dashboard_routes and "if sync_settings_state(data, settings):" in bot_routes
checks["scan_rows_expose_passed_boolean"] = '"passed": bool(analysis.get("passed"))' in analysis
checks["zero_trade_count_is_rejected_in_lightweight"] = 'if _safe_int(row.get("trade_count")) < cfg["min_trade_count"]' in analysis
checks["zero_trade_count_is_rejected_in_universe_guard"] = 'if trade_count < min_trade_count' in universe

failed = [key for key, value in checks.items() if not value]
status = "ok" if not failed else "failed"
report = {
    "status": status,
    "failed": failed,
    "checks": checks,
}

out_json = ROOT / "docs" / "LEVEL1_40_39_3_COINFILTER_SETTINGS_CONTRACT_AUDIT.json"
out_md = ROOT / "docs" / "LEVEL1_40_39_3_COINFILTER_SETTINGS_CONTRACT_AUDIT.md"
out_json.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
out_md.write_text(
    "# LEVEL1_40_39_3 CoinFilter Settings Contract Audit\n\n"
    f"status={status}\n\n"
    + "\n".join(f"- {key}: {value}" for key, value in checks.items())
    + "\n",
    encoding="utf-8",
)

if failed:
    print("LEVEL1_40_39_3_COINFILTER_SETTINGS_CONTRACT_AUDIT_FAILED")
    print("failed=" + ",".join(failed))
    raise SystemExit(1)

print("LEVEL1_40_39_3_COINFILTER_SETTINGS_CONTRACT_AUDIT_OK")
print("status=ok")
print("shadow_settings_mirror=true")
print("scan_settings_snapshot=true")
print("dashboard_bundle_settings_contract=true")
print("scan_rows_passed_boolean=true")
print("zero_trade_count_rejected=true")
print(f"json={out_json.relative_to(ROOT)}")
print(f"markdown={out_md.relative_to(ROOT)}")
