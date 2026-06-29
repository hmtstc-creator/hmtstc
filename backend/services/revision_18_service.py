from __future__ import annotations

from services.rule_schema_service import build_rule_governance_report, build_rule_schema_contract
from services.rule_engine import example_rules, list_rules


def build_rule_editor_v3_readiness(username: str) -> dict:
    return {
        "status": "ok",
        "features": {
            "type_locked_tabs": True,
            "blank_filter_draft": True,
            "blank_strategy_draft": True,
            "schema_contract_panel": True,
            "field_based_validation": True,
            "version_history_panel": True,
            "diff_preview": True,
            "restore_version_action": True,
            "import_export_governance": True,
            "paper_lab_activation_guard": True,
        },
        "required_files": [
            "frontend/js/pages/ruleEditor.js",
            "frontend/js/app/rules.js",
            "backend/services/rule_schema_service.py",
            "backend/routes/rule_routes.py",
        ],
        "methodology": "Rule editörü artık kontrolsüz JSON alanı değil; schema, diff, version ve Paper Lab etkisiyle yönetilen governance ekranıdır.",
    }


def build_rule_import_export_readiness(username: str) -> dict:
    payload = list_rules(username)
    examples = example_rules()
    return {
        "status": "ok",
        "export_ready": True,
        "import_validation_required": True,
        "overwrite_default": False,
        "collision_policy": "overwrite=false ise yeni kopya oluşturulur",
        "rule_count": len(payload.get("rules", []) or []),
        "example_filter_available": bool(examples.get("filter")),
        "example_strategy_available": bool(examples.get("strategy")),
    }


def build_revision_18_quality_report(username: str) -> dict:
    governance = build_rule_governance_report(username)
    editor = build_rule_editor_v3_readiness(username)
    import_export = build_rule_import_export_readiness(username)
    contract = build_rule_schema_contract()
    blockers = []
    if governance.get("invalid_count", 0) > 0:
        blockers.append("invalid_rules_present")
    return {
        "revision": 18,
        "status": "ok" if not blockers else "review",
        "theme": "Rule Editor V3 + Schema Governance + Diff/Restore + Import/Export Safety",
        "blockers": blockers,
        "rule_governance": governance,
        "rule_editor_v3": editor,
        "import_export": import_export,
        "schema_contract": contract,
        "next_revision": "Rev19 = Reports + Paper Lab karar ekranı + attribution/execution quality görünümü",
    }
