#!/usr/bin/env python3
from __future__ import annotations

import importlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
STORAGE = BACKEND / "core" / "storage.py"
BOT_ROUTES = BACKEND / "routes" / "bot_routes.py"
JSON_OUT = ROOT / "docs" / "LEVEL1_40_35_LAST_SCAN_CONTRACT_PRESERVATION_AUDIT.json"
MD_OUT = ROOT / "docs" / "LEVEL1_40_35_LAST_SCAN_CONTRACT_PRESERVATION_AUDIT.md"
PRIOR_AUDITS = [
    ROOT / "docs" / f"LEVEL1_40_{number}_{name}_AUDIT.json"
    for number, name in [
        (20, "LIVE_STARTUP_RULES_HYDRATION"),
        (21, "AUTH_RESTORE_TRUTH"),
        (22, "COINFILTER_RULES_PAPERLAB"),
        (23, "RULES_PAPERLAB_INDEPENDENCE"),
        (24, "PAPERLAB_AUTONOMOUS_ENGINE"),
        (25, "PAPERLAB_PERSISTENCE"),
        (26, "PAPERLAB_HYDRATION_STABILITY"),
        (27, "RUNTIME_HEALTH_PAPERLAB_STORE"),
        (28, "RUNTIME_HEALTH_PAPERLAB_USER_RESOLUTION"),
        (29, "COINFILTER_PERSISTENCE_AND_8H_REPORT"),
        (30, "BOT_RUNTIME_HEARTBEAT_TRUTH"),
        (31, "BOT_RESTORE_REAL_LOOP"),
        (32, "BOT_RESTORE_FIRST_TICK"),
        (33, "COINFILTER_FINAL_PIPELINE"),
        (34, "COINFILTER_TEST_SCAN_TIMEOUT"),
    ]
]


def _load_text(path: Path) -> str:
    if not path.exists():
        raise FileNotFoundError(f"Missing required input: {path.relative_to(ROOT)}")
    return path.read_text(encoding="utf-8")


def _load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(f"Missing required input: {path.relative_to(ROOT)}")
    return json.loads(path.read_text(encoding="utf-8"))


def _section(text: str, start: str, end: str) -> str:
    start_index = text.find(start)
    if start_index < 0:
        return ""
    end_index = text.find(end, start_index + len(start))
    return text[start_index:] if end_index < 0 else text[start_index:end_index]


def _runtime_probe() -> dict[str, Any]:
    sys.path.insert(0, str(BACKEND))
    storage = importlib.import_module("core.storage")
    routes = importlib.import_module("routes.bot_routes")
    pipeline = {
        "market_universe": {"total_seen": 88},
        "coinfilter": {"passed": 12},
        "strategy": {"status": "not_run_in_coinfilter_test"},
    }
    history_scan = {
        "status": "ok",
        "live": True,
        "source": "binance",
        "time": "2026-06-12T22:35:57",
        "scan_id": "scan-history",
        "mode": "coinfilter_test_scan",
        "test_scan": True,
        "scanned": 88,
        "eligible_universe_count": 88,
        "universe_total_seen": 120,
        "universe_rejected_count": 32,
        "universe_rejection_breakdown": {"stable_coin": 20},
        "candidates_count": 12,
        "pipeline": pipeline,
        "scan_rows": [{"symbol": "BTCUSDT"}],
    }
    legacy_last_scan = {
        "status": "ok",
        "live": True,
        "source": "binance",
        "time": "2026-06-12T22:35:57",
        "scan_id": "scan-history",
        "scanned": 88,
        "candidates_count": 12,
        "scan_rows": [{"symbol": "BTCUSDT"}],
    }
    repaired = storage.normalize_shadow_state({
        "last_scan": legacy_last_scan,
        "scan_history": [history_scan],
    })
    repaired_scan = repaired.get("last_scan") or {}
    payload = routes._last_scan_payload("audit", repaired, {})

    protected = storage.normalize_shadow_state({
        "last_scan": {
            **legacy_last_scan,
            "pipeline": {"existing": True},
            "mode": "normal_bot_scan",
        },
        "scan_history": [{**history_scan, "time": "2026-06-12T22:36:57"}],
    }).get("last_scan") or {}

    return {
        "repaired_test_scan": repaired_scan.get("test_scan"),
        "repaired_mode": repaired_scan.get("mode"),
        "repaired_pipeline": repaired_scan.get("pipeline"),
        "repaired_eligible_universe_count": repaired_scan.get("eligible_universe_count"),
        "repaired_universe_total_seen": repaired_scan.get("universe_total_seen"),
        "repaired_universe_rejected_count": repaired_scan.get("universe_rejected_count"),
        "repaired_universe_rejection_breakdown": repaired_scan.get("universe_rejection_breakdown"),
        "payload_test_scan": payload.get("test_scan"),
        "payload_scan_mode": payload.get("scan_mode"),
        "payload_pipeline": payload.get("pipeline"),
        "existing_pipeline_preserved": protected.get("pipeline") == {"existing": True},
        "existing_mode_preserved": protected.get("mode") == "normal_bot_scan",
    }


def build_report() -> dict[str, Any]:
    storage_text = _load_text(STORAGE)
    routes_text = _load_text(BOT_ROUTES)
    normalize_fn = _section(storage_text, "def normalize_shadow_state", "def get_user_container")
    payload_fn = _section(routes_text, "def _last_scan_payload", '@router.get("/scan")')
    prior_statuses = {path.stem: _load_json(path).get("status") for path in PRIOR_AUDITS}
    probe = _runtime_probe()

    universe_fields = [
        "eligible_universe_count",
        "universe_total_seen",
        "universe_rejected_count",
        "universe_rejection_breakdown",
    ]
    checks = {
        "normalize_last_scan_preserves_test_scan": '"test_scan": bool(last_scan.get("test_scan", False))' in normalize_fn and probe["repaired_test_scan"] is True,
        "normalize_last_scan_preserves_mode": '"mode": last_scan.get("mode")' in normalize_fn and probe["repaired_mode"] == "coinfilter_test_scan",
        "normalize_last_scan_preserves_pipeline": '"pipeline": last_scan.get("pipeline", {})' in normalize_fn and bool(probe["repaired_pipeline"]),
        "normalize_last_scan_preserves_universe_fields": all(field in normalize_fn for field in universe_fields) and probe["repaired_universe_total_seen"] == 120,
        "last_scan_payload_returns_test_scan": '"test_scan": bool(last_scan.get("test_scan", False))' in payload_fn and probe["payload_test_scan"] is True,
        "last_scan_payload_returns_pipeline": '"pipeline": last_scan.get("pipeline", {})' in payload_fn and bool(probe["payload_pipeline"]),
        "last_scan_payload_returns_scan_mode": '"scan_mode": last_scan.get("mode")' in payload_fn and probe["payload_scan_mode"] == "coinfilter_test_scan",
        "runtime_repair_logic_present": all(value in normalize_fn for value in ["latest_history_scan", "history_is_current", "not last_scan.get(\"pipeline\")"]),
        "runtime_repair_restores_contract": all([
            probe["repaired_eligible_universe_count"] == 88,
            probe["repaired_universe_rejected_count"] == 32,
            probe["repaired_universe_rejection_breakdown"] == {"stable_coin": 20},
        ]),
        "runtime_repair_does_not_overwrite_existing_pipeline": probe["existing_pipeline_preserved"] and probe["existing_mode_preserved"],
        "previous_40_20_to_40_34_status_ok": all(status == "ok" for status in prior_statuses.values()),
    }
    blockers = [f"{name}=false" for name, value in checks.items() if not value]
    return {
        "status": "blocker" if blockers else "ok",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        **checks,
        "runtime_probe": probe,
        "prior_statuses": prior_statuses,
        "blockers": blockers,
        "recommended_next_actions": [
            "Deploy sonrasi test scan ve last-scan response degerlerini birebir karsilastir.",
            "Mevcut runtime store ilk load sonrasi pipeline contract repair sonucunu dogrula.",
            "Runtime store dosyalarini Git'e ekleme.",
        ],
    }


def _yn(value: bool) -> str:
    return "evet" if value else "hayir"


def write_markdown(report: dict[str, Any]) -> None:
    lines = [
        "# Level1 40.35 Last Scan Contract Preservation Audit",
        "",
        "## Ozet",
        "",
        f"- Durum: `{report['status']}`",
        f"- Pipeline korunuyor: `{_yn(report['normalize_last_scan_preserves_pipeline'])}`",
        f"- Runtime repair: `{_yn(report['runtime_repair_restores_contract'])}`",
        f"- Existing pipeline overwrite yok: `{_yn(report['runtime_repair_does_not_overwrite_existing_pipeline'])}`",
        f"- Onceki 40.20-40.34 zinciri: `{_yn(report['previous_40_20_to_40_34_status_ok'])}`",
        "",
        "## Kontroller",
        "",
    ]
    for key, value in report.items():
        if isinstance(value, bool):
            lines.append(f"- {key}: `{_yn(value)}`")
    lines.extend(["", "## Blocker Listesi", ""])
    if report["blockers"]:
        lines.extend(f"- BLOCKER: {blocker}" for blocker in report["blockers"])
    else:
        lines.append("Blocker yok.")
    lines.extend(["", "## Sonuc", ""])
    lines.append("Last scan contract preservation kalite kapisi temiz." if report["status"] == "ok" else "Last scan contract preservation kalite kapisi blocker durumunda.")
    lines.append("")
    MD_OUT.write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    try:
        report = build_report()
        JSON_OUT.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        write_markdown(report)
    except Exception as exc:
        print(f"LEVEL1_40_35_LAST_SCAN_CONTRACT_PRESERVATION_AUDIT_ERROR: {exc}", file=sys.stderr)
        return 1

    marker = {
        "ok": "LEVEL1_40_35_LAST_SCAN_CONTRACT_PRESERVATION_AUDIT_OK",
        "blocker": "LEVEL1_40_35_LAST_SCAN_CONTRACT_PRESERVATION_AUDIT_BLOCKER",
    }[report["status"]]
    print(marker)
    print(f"status={report['status']}")
    print(f"normalize_last_scan_preserves_pipeline={str(report['normalize_last_scan_preserves_pipeline']).lower()}")
    print(f"runtime_repair_restores_contract={str(report['runtime_repair_restores_contract']).lower()}")
    print(f"last_scan_payload_returns_pipeline={str(report['last_scan_payload_returns_pipeline']).lower()}")
    print(f"previous_40_20_to_40_34_status_ok={str(report['previous_40_20_to_40_34_status_ok']).lower()}")
    print(f"json={JSON_OUT.relative_to(ROOT)}")
    print(f"markdown={MD_OUT.relative_to(ROOT)}")
    return 1 if report["status"] == "blocker" else 0


if __name__ == "__main__":
    raise SystemExit(main())
