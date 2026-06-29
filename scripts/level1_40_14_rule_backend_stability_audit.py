#!/usr/bin/env python3
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
RULE_ROUTES = ROOT / "backend" / "routes" / "rule_routes.py"
RULE_ENGINE = ROOT / "backend" / "services" / "rule_engine.py"
RULES_JS = ROOT / "frontend" / "js" / "app" / "rules.js"
CONTRACT_DIFF_PATH = ROOT / "docs" / "LEVEL1_40_08_API_CONTRACT_DIFF.json"
RULE_SELECTION_AUDIT_PATH = ROOT / "docs" / "LEVEL1_40_13_RULE_SELECTION_PERSISTENCE_AUDIT.json"
JSON_OUT = ROOT / "docs" / "LEVEL1_40_14_RULE_BACKEND_STABILITY_AUDIT.json"
MD_OUT = ROOT / "docs" / "LEVEL1_40_14_RULE_BACKEND_STABILITY_AUDIT.md"


def _load_text(path: Path) -> str:
    if not path.exists():
        raise FileNotFoundError(f"Missing required input: {path.relative_to(ROOT)}")
    return path.read_text(encoding="utf-8")


def _load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(f"Missing required input: {path.relative_to(ROOT)}")
    return json.loads(path.read_text(encoding="utf-8"))


def _runtime_policy(diff: dict[str, Any]) -> dict[str, list[Any]]:
    policy = diff.get("runtime_policy") if isinstance(diff.get("runtime_policy"), dict) else {}
    return {
        "runtime_leaks": diff.get("runtime_leaks") if isinstance(diff.get("runtime_leaks"), list) else [],
        "tracked_runtime_stores": policy.get("tracked_runtime_stores") if isinstance(policy.get("tracked_runtime_stores"), list) else [],
        "unignored_runtime_stores": policy.get("unignored_runtime_stores") if isinstance(policy.get("unignored_runtime_stores"), list) else [],
    }


def build_report(rule_routes: str, rule_engine: str, rules_js: str, diff: dict[str, Any], selection: dict[str, Any]) -> dict[str, Any]:
    combined = rule_routes + "\n" + rule_engine
    activate_paper_lab_route_present = '@router.post("/activate-paper-lab")' in rule_routes and "def activate_rules" in rule_routes
    activate_payload_normalization_present = "_payload_dict(payload)" in rule_routes and "_normalize_optional_id_list" in rule_routes
    selected_filter_ids_normalized = "selected_filter_ids = _normalize_optional_id_list" in rule_routes and "selected_filter_ids" in rule_engine
    selected_strategy_ids_normalized = "selected_strategy_ids = _normalize_optional_id_list" in rule_routes and "selected_strategy_ids" in rule_engine
    empty_filter_strategy_http400_present = (
        "Paper Lab için en az 1 filtre seçilmelidir." in combined
        and "Paper Lab için en az 1 strateji seçilmelidir." in combined
        and "HTTPException(status_code=400" in rule_routes
    )
    activate_response_selected_filter_ids_present = 'result.setdefault("selected_filter_ids"' in rule_routes and '"selected_filter_ids": final_filter_ids' in rule_engine
    activate_response_selected_strategy_ids_present = 'result.setdefault("selected_strategy_ids"' in rule_routes and '"selected_strategy_ids": final_strategy_ids' in rule_engine
    activate_response_model_count_present = 'result.setdefault("model_count"' in rule_routes and '"model_count": activation_item["model_count"]' in rule_engine
    activate_response_activation_present = 'result.setdefault("activation"' in rule_routes and '"activation": activation_item' in rule_engine
    rule_save_validation_present = all(
        text in rule_routes
        for text in [
            "Payload içinde rule alanı zorunludur.",
            "rule object olmalıdır.",
            "rule.id zorunludur.",
            "rule.type filter veya strategy olmalıdır.",
        ]
    )
    rule_get_validation_present = "rule_id = str(payload.get(\"rule_id\")" in rule_routes and "status_code=404, detail=\"Düzeltilecek filtre/strateji bulunamadı." in rule_routes
    rule_delete_validation_present = "delete_rule_post_payload" in rule_routes and "rule_id = str(rule_id or \"\").strip()" in rule_routes and 'result["rule_id"] = rule_id' in rule_routes
    http500_detail_present = all(
        text in rule_routes
        for text in [
            "Rule save hatası:",
            "Rule get hatası:",
            "Rule delete hatası:",
            "Paper Lab aktivasyon hatası:",
        ]
    )
    audit_failure_isolated = (
        "_safe_append_audit" in rule_routes
        and "audit_written" in rule_routes
        and "catch (auditError)" in rules_js
        and "audit yazılamadı" in rules_js
    )

    runtime = _runtime_policy(diff)
    contract_missing_path_count = int(diff.get("missing_path_count") or 0)
    contract_method_mismatch_count = int(diff.get("method_mismatch_count") or 0)
    runtime_leak_count = len(runtime["runtime_leaks"])
    tracked_runtime_store_count = len(runtime["tracked_runtime_stores"])
    unignored_runtime_store_count = len(runtime["unignored_runtime_stores"])
    selection_status = str(selection.get("status") or "unknown")

    blockers: list[str] = []
    for name, value in [
        ("activate_paper_lab_route_present", activate_paper_lab_route_present),
        ("activate_response_selected_filter_ids_present", activate_response_selected_filter_ids_present),
        ("activate_response_selected_strategy_ids_present", activate_response_selected_strategy_ids_present),
        ("activate_response_model_count_present", activate_response_model_count_present),
        ("activate_response_activation_present", activate_response_activation_present),
    ]:
        if not value:
            blockers.append(f"{name}=false")
    if selection_status != "ok":
        blockers.append(f"40.13 rule selection persistence status is {selection_status}")
    if contract_missing_path_count:
        blockers.append(f"Contract diff has missing_path_count={contract_missing_path_count}")
    if contract_method_mismatch_count:
        blockers.append(f"Contract diff has method_mismatch_count={contract_method_mismatch_count}")
    if runtime_leak_count:
        blockers.append(f"Runtime leak count is {runtime_leak_count}")
    if tracked_runtime_store_count:
        blockers.append(f"Tracked runtime store count is {tracked_runtime_store_count}")
    if unignored_runtime_store_count:
        blockers.append(f"Unignored runtime store count is {unignored_runtime_store_count}")

    review_items: list[str] = []
    for name, value in [
        ("activate_payload_normalization_present", activate_payload_normalization_present),
        ("selected_filter_ids_normalized", selected_filter_ids_normalized),
        ("selected_strategy_ids_normalized", selected_strategy_ids_normalized),
        ("empty_filter_strategy_http400_present", empty_filter_strategy_http400_present),
        ("rule_save_validation_present", rule_save_validation_present),
        ("rule_get_validation_present", rule_get_validation_present),
        ("rule_delete_validation_present", rule_delete_validation_present),
        ("http500_detail_present", http500_detail_present),
        ("audit_failure_isolated", audit_failure_isolated),
    ]:
        if not value:
            review_items.append(f"{name}=false")

    status = "blocker" if blockers else ("review" if review_items else "ok")

    return {
        "status": status,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source_rule_routes": str(RULE_ROUTES.relative_to(ROOT)),
        "source_rule_engine": str(RULE_ENGINE.relative_to(ROOT)),
        "source_rules_js": str(RULES_JS.relative_to(ROOT)),
        "source_contract_diff": str(CONTRACT_DIFF_PATH.relative_to(ROOT)),
        "source_rule_selection_persistence": str(RULE_SELECTION_AUDIT_PATH.relative_to(ROOT)),
        "activate_paper_lab_route_present": activate_paper_lab_route_present,
        "activate_payload_normalization_present": activate_payload_normalization_present,
        "selected_filter_ids_normalized": selected_filter_ids_normalized,
        "selected_strategy_ids_normalized": selected_strategy_ids_normalized,
        "empty_filter_strategy_http400_present": empty_filter_strategy_http400_present,
        "activate_response_selected_filter_ids_present": activate_response_selected_filter_ids_present,
        "activate_response_selected_strategy_ids_present": activate_response_selected_strategy_ids_present,
        "activate_response_model_count_present": activate_response_model_count_present,
        "activate_response_activation_present": activate_response_activation_present,
        "rule_save_validation_present": rule_save_validation_present,
        "rule_get_validation_present": rule_get_validation_present,
        "rule_delete_validation_present": rule_delete_validation_present,
        "http500_detail_present": http500_detail_present,
        "audit_failure_isolated": audit_failure_isolated,
        "rule_selection_persistence_status": selection_status,
        "contract_missing_path_count": contract_missing_path_count,
        "contract_method_mismatch_count": contract_method_mismatch_count,
        "runtime_leak_count": runtime_leak_count,
        "tracked_runtime_store_count": tracked_runtime_store_count,
        "unignored_runtime_store_count": unignored_runtime_store_count,
        "blockers": blockers,
        "review_items": review_items,
        "recommended_next_actions": [
            "Keep 40.14 in the quality chain after 40.13 before changing rule save or Paper Lab endpoints.",
            "Keep Paper Lab model combination math unchanged unless a dedicated model package is approved.",
            "Keep audit/log write failures isolated from rule save and Paper Lab activation success.",
            "Return clear HTTP 400 details for invalid rule payloads or empty Paper Lab selections.",
        ],
    }


def _yn(value: bool) -> str:
    return "evet" if value else "hayir"


def write_markdown(report: dict[str, Any]) -> None:
    lines: list[str] = []
    lines.append("# Level1 40.14 Rule Backend Stability Audit")
    lines.append("")
    lines.append("## Ozet")
    lines.append("")
    lines.append(f"- Durum: `{report['status']}`")
    lines.append(f"- Activate Paper Lab route: `{_yn(report['activate_paper_lab_route_present'])}`")
    lines.append(f"- Payload normalization: `{_yn(report['activate_payload_normalization_present'])}`")
    lines.append(f"- Rule save validation: `{_yn(report['rule_save_validation_present'])}`")
    lines.append(f"- Audit izolasyonu: `{_yn(report['audit_failure_isolated'])}`")
    lines.append("")
    lines.append("## Activate Paper Lab Contract")
    lines.append("")
    lines.append(f"- selected_filter_ids normalize: `{_yn(report['selected_filter_ids_normalized'])}`")
    lines.append(f"- selected_strategy_ids normalize: `{_yn(report['selected_strategy_ids_normalized'])}`")
    lines.append(f"- Bos filtre/strateji HTTP 400: `{_yn(report['empty_filter_strategy_http400_present'])}`")
    lines.append(f"- Response selected_filter_ids: `{_yn(report['activate_response_selected_filter_ids_present'])}`")
    lines.append(f"- Response selected_strategy_ids: `{_yn(report['activate_response_selected_strategy_ids_present'])}`")
    lines.append(f"- Response model_count: `{_yn(report['activate_response_model_count_present'])}`")
    lines.append(f"- Response activation: `{_yn(report['activate_response_activation_present'])}`")
    lines.append("")
    lines.append("## Rule Save/Get/Delete Contract")
    lines.append("")
    lines.append(f"- Save validation: `{_yn(report['rule_save_validation_present'])}`")
    lines.append(f"- Get validation: `{_yn(report['rule_get_validation_present'])}`")
    lines.append(f"- Delete validation: `{_yn(report['rule_delete_validation_present'])}`")
    lines.append(f"- HTTP 500 detail: `{_yn(report['http500_detail_present'])}`")
    lines.append("")
    lines.append("## Audit Izolasyonu")
    lines.append("")
    lines.append(f"- Audit/log hatasi ana sonucu bozmuyor: `{_yn(report['audit_failure_isolated'])}`")
    lines.append("")
    lines.append("## Contract / Runtime Guard")
    lines.append("")
    lines.append(f"- 40.13 status: `{report['rule_selection_persistence_status']}`")
    lines.append(f"- Missing path: `{report['contract_missing_path_count']}`")
    lines.append(f"- Method mismatch: `{report['contract_method_mismatch_count']}`")
    lines.append(f"- Runtime leak: `{report['runtime_leak_count']}`")
    lines.append(f"- Tracked runtime store: `{report['tracked_runtime_store_count']}`")
    lines.append(f"- Unignored runtime store: `{report['unignored_runtime_store_count']}`")
    lines.append("")
    lines.append("## Blocker / Review Listesi")
    lines.append("")
    if report["blockers"]:
        for blocker in report["blockers"]:
            lines.append(f"- BLOCKER: {blocker}")
    if report["review_items"]:
        for item in report["review_items"]:
            lines.append(f"- REVIEW: {item}")
    if not report["blockers"] and not report["review_items"]:
        lines.append("Blocker veya review item yok.")
    lines.append("")
    lines.append("## Sonuc")
    lines.append("")
    if report["status"] == "ok":
        lines.append("Rules ve Paper Lab backend stability contract temiz.")
    elif report["status"] == "review":
        lines.append("Rules backend stability icin manuel inceleme gerektiren statik bulgular var.")
    else:
        lines.append("Rules backend stability veya contract guard blocker durumunda.")
    lines.append("")
    lines.append("## Paket 10 Icin Onerilen Devam")
    lines.append("")
    for action in report["recommended_next_actions"]:
        lines.append(f"- {action}")
    lines.append("")
    MD_OUT.write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    try:
        rule_routes = _load_text(RULE_ROUTES)
        rule_engine = _load_text(RULE_ENGINE)
        rules_js = _load_text(RULES_JS)
        diff = _load_json(CONTRACT_DIFF_PATH)
        selection = _load_json(RULE_SELECTION_AUDIT_PATH)
        report = build_report(rule_routes, rule_engine, rules_js, diff, selection)
        JSON_OUT.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        write_markdown(report)
    except Exception as exc:
        print(f"LEVEL1_40_14_RULE_BACKEND_STABILITY_AUDIT_ERROR: {exc}", file=sys.stderr)
        return 1

    marker = {
        "ok": "LEVEL1_40_14_RULE_BACKEND_STABILITY_AUDIT_OK",
        "review": "LEVEL1_40_14_RULE_BACKEND_STABILITY_AUDIT_REVIEW",
        "blocker": "LEVEL1_40_14_RULE_BACKEND_STABILITY_AUDIT_BLOCKER",
    }[report["status"]]

    print(marker)
    print(f"status={report['status']}")
    print(f"activate_paper_lab_route_present={str(report['activate_paper_lab_route_present']).lower()}")
    print(f"activate_payload_normalization_present={str(report['activate_payload_normalization_present']).lower()}")
    print(f"rule_save_validation_present={str(report['rule_save_validation_present']).lower()}")
    print(f"rule_get_validation_present={str(report['rule_get_validation_present']).lower()}")
    print(f"rule_delete_validation_present={str(report['rule_delete_validation_present']).lower()}")
    print(f"audit_failure_isolated={str(report['audit_failure_isolated']).lower()}")
    print(f"json={JSON_OUT.relative_to(ROOT)}")
    print(f"markdown={MD_OUT.relative_to(ROOT)}")

    return 1 if report["status"] == "blocker" else 0


if __name__ == "__main__":
    raise SystemExit(main())
