from fastapi import APIRouter, Depends, HTTPException

from core.auth import require_admin, require_user
from core.config import DEFAULT_USER
from core.storage import append_audit, load_shadow, save_shadow
from services.rule_engine import (
    OWNER_RULE_USERNAME,
    activate_paper_lab_rules,
    analyze_compatibility,
    build_persistent_paper_lab_status,
    delete_rule,
    example_rules,
    export_rules,
    get_rule,
    get_rule_versions,
    restore_rule_version,
    import_rules,
    list_rules,
    save_rule_selection,
    save_rule,
    validate_rule,
)

from services.rule_schema_service import (
    build_rule_diff,
    build_rule_governance_report,
    build_rule_schema_contract,
    validate_rule_schema,
)
from services.rule_governance_service import (
    build_rule_final_governance_report,
    build_rule_impact_report,
    build_rule_lineage_report,
    build_rule_rollback_preview,
)
from services.rule_settings_governance_service import (
    build_rule_danger_warnings,
    build_rule_governance_evidence,
    build_rule_governance_schema,
    build_rule_settings_governance_quality,
)
from services.analysis_service import build_candidate_handoff
from services.model_scoring_service import build_strategy_runtime_contract, evaluate_strategy_candidates


router = APIRouter(prefix="/api/rules", tags=["rules"])


def require_rule_owner(current_user: dict = Depends(require_admin)) -> dict:
    return current_user


def require_rule_user(current_user: dict = Depends(require_user)) -> dict:
    return current_user


def current_username(current_user: dict) -> str:
    username = str(current_user.get("username") or "").strip()
    return username or DEFAULT_USER


def catalog_owner_username() -> str:
    return OWNER_RULE_USERNAME


def _payload_dict(payload) -> dict:
    return payload if isinstance(payload, dict) else {}


def _normalize_optional_id_list(value):
    if not isinstance(value, list):
        return None

    clean = []
    for raw_id in value:
        item_id = str(raw_id or "").strip()
        if item_id and item_id not in clean:
            clean.append(item_id)
    return clean


def _paper_lab_error(error: Exception) -> str:
    text = str(error or "").strip()
    return text[:240] or "bilinmeyen hata"


def _safe_append_audit(data: dict, event: str, status: str, message: str, *, meta: dict, user: str) -> bool:
    try:
        append_audit(data, event, status, message, meta=meta, user=user)
        save_shadow(data, user)
        return True
    except Exception:
        return False


@router.get("")
def get_rules(current_user: dict = Depends(require_rule_user)):
    return list_rules(current_username(current_user))


@router.get("/examples")
def get_examples(current_user: dict = Depends(require_rule_user)):
    return example_rules()


@router.get("/activation-log")
def get_activation_log(current_user: dict = Depends(require_rule_user)):
    payload = list_rules(current_username(current_user))
    return {
        "status": "ok",
        "activation_log": payload.get("activation_log", []),
        "last_activation_at": payload.get("last_activation_at"),
    }


@router.get("/paper-lab/status")
def get_paper_lab_persistent_status(current_user: dict = Depends(require_rule_user)):
    return build_persistent_paper_lab_status(current_username(current_user))


@router.get("/runtime-contract")
def strategy_runtime_contract(current_user: dict = Depends(require_rule_user)):
    return build_strategy_runtime_contract(current_username(current_user))


@router.post("/runtime-evaluate")
def strategy_runtime_evaluate(payload: dict | None = None, current_user: dict = Depends(require_rule_user)):
    user = current_username(current_user)
    incoming = _payload_dict(payload)
    if isinstance(incoming.get("candidate_handoff"), dict):
        handoff = incoming["candidate_handoff"]
    else:
        runtime = load_shadow(user)
        handoff = build_candidate_handoff(runtime.get("last_scan") or {})
    return evaluate_strategy_candidates(user, handoff)


@router.post("/validate")
def validate_rule_payload(payload: dict, current_user: dict = Depends(require_rule_owner)):
    rule = payload.get("rule") if isinstance(payload, dict) and "rule" in payload else payload
    return validate_rule(rule)


@router.post("/save")
def save_rule_payload(payload: dict, current_user: dict = Depends(require_rule_owner)):
    user = catalog_owner_username()
    if not isinstance(payload, dict):
        raise HTTPException(status_code=400, detail="Rule save payload object olmalıdır.")

    if "rule" not in payload:
        raise HTTPException(status_code=400, detail="Payload içinde rule alanı zorunludur.")

    rule = payload.get("rule")
    if not isinstance(rule, dict) or isinstance(rule, list):
        raise HTTPException(status_code=400, detail="rule object olmalıdır.")

    if not str(rule.get("id") or "").strip():
        raise HTTPException(status_code=400, detail="rule.id zorunludur.")

    if str(rule.get("type") or "").strip() not in {"filter", "strategy"}:
        raise HTTPException(status_code=400, detail="rule.type filter veya strategy olmalıdır.")

    try:
        schema_result = validate_rule_schema(rule)
        if not schema_result.get("valid"):
            raise ValueError(str(schema_result.get("errors") or "Rule schema validation failed"))
        result = save_rule(user, rule)
        data = load_shadow(user)
        saved = result.get("saved", {})
        audit_written = _safe_append_audit(
            data,
            "rule.save",
            "ok",
            f"Rule kaydedildi: {saved.get('id')}",
            meta={"category": "rule", "severity": "notice", "rule_type": saved.get("type"), "rule_id": saved.get("id"), "before": result.get("previous"), "after": saved, "endpoint": "/api/rules/save", "role": current_user.get("role"), "version": saved.get("version"), "schema_valid": True, "schema_warnings": schema_result.get("warnings", []), "governance_version": "rev26"},
            user=user,
        )
        if not audit_written:
            result["warning"] = "Rule kaydedildi ancak audit/log yazılamadı."
        return result
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error))
    except HTTPException:
        raise
    except Exception as error:
        raise HTTPException(status_code=500, detail=f"Rule save hatası: {_paper_lab_error(error)}")


@router.post("/delete")
def delete_rule_post_payload(payload: dict, current_user: dict = Depends(require_rule_owner)):
    payload = _payload_dict(payload)
    rule_id = str(payload.get("rule_id") or "").strip()
    if not rule_id:
        raise HTTPException(status_code=400, detail="Silinecek filtre/strateji id gerekli.")
    return delete_rule_payload(rule_id, current_user=current_user)


@router.post("/get")
def get_rule_payload(payload: dict, current_user: dict = Depends(require_rule_owner)):
    payload = _payload_dict(payload)
    rule_id = str(payload.get("rule_id") or "").strip()
    if not rule_id:
        raise HTTPException(status_code=400, detail="Düzeltilecek filtre/strateji id gerekli.")
    try:
        rule = get_rule(catalog_owner_username(), rule_id)
        if not rule:
            raise HTTPException(status_code=404, detail="Düzeltilecek filtre/strateji bulunamadı.")
        return {"status": "ok", "rule": rule}
    except HTTPException:
        raise
    except Exception as error:
        raise HTTPException(status_code=500, detail=f"Rule get hatası: {_paper_lab_error(error)}")


@router.post("/selection")
def save_rule_selection_payload(payload: dict, current_user: dict = Depends(require_rule_user)):
    payload = _payload_dict(payload)

    if not isinstance(payload.get("selected_filter_ids"), list):
        raise HTTPException(status_code=400, detail="selected_filter_ids list olmalıdır.")

    if not isinstance(payload.get("selected_strategy_ids"), list):
        raise HTTPException(status_code=400, detail="selected_strategy_ids list olmalıdır.")

    try:
        result = save_rule_selection(
            current_username(current_user),
            selected_filter_ids=_normalize_optional_id_list(payload.get("selected_filter_ids")) or [],
            selected_strategy_ids=_normalize_optional_id_list(payload.get("selected_strategy_ids")) or [],
        )
        return result
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error))
    except Exception as error:
        raise HTTPException(status_code=500, detail=f"Rule selection save hatası: {_paper_lab_error(error)}")


@router.delete("/{rule_id}")
def delete_rule_payload(rule_id: str, current_user: dict = Depends(require_rule_owner)):
    user = catalog_owner_username()
    rule_id = str(rule_id or "").strip()
    if not rule_id:
        raise HTTPException(status_code=400, detail="Silinecek filtre/strateji id gerekli.")
    try:
        result = delete_rule(user, rule_id)
        if int(result.get("deleted") or 0) < 1:
            raise HTTPException(status_code=404, detail="Silinecek filtre/strateji bulunamadı.")
        result["deleted_count"] = int(result.get("deleted") or 0)
        result["deleted"] = True
        result["rule_id"] = rule_id
        data = load_shadow(user)
        audit_written = _safe_append_audit(data, "rule.delete", "ok", f"Rule silindi: {rule_id}", meta={"category": "rule", "severity": "warning", "rule_id": rule_id, "endpoint": f"/api/rules/{rule_id}", "role": current_user.get("role")}, user=user)
        if not audit_written:
            result["warning"] = "Rule silindi ancak audit/log yazılamadı."
        return result
    except HTTPException:
        raise
    except Exception as error:
        raise HTTPException(status_code=500, detail=f"Rule delete hatası: {_paper_lab_error(error)}")


@router.post("/analyze")
def analyze_rules(payload: dict, current_user: dict = Depends(require_rule_owner)):
    filter_rule = payload.get("filter") or payload.get("filter_rule")
    strategy_rule = payload.get("strategy") or payload.get("strategy_rule")
    if not filter_rule or not strategy_rule:
        raise HTTPException(status_code=400, detail="filter ve strategy rule gerekli.")
    return analyze_compatibility(filter_rule, strategy_rule)


@router.post("/activate-paper-lab")
def activate_rules(payload: dict | None = None, current_user: dict = Depends(require_rule_user)):
    payload = _payload_dict(payload)

    try:
        result = activate_paper_lab_rules(current_username(current_user))
        result.setdefault("status", "ok")
        result.setdefault("mode", "paper_lab")
        result.setdefault("paper_lab_filter_ids", [])
        result.setdefault("paper_lab_strategy_ids", [])
        result.setdefault("paper_lab_candidate_count", 0)
        result.setdefault("accepted_combinations", 0)
        result.setdefault("rejected_combinations", 0)
        result.setdefault("model_count", 0)
        result.setdefault("activation", {"logs": []})
        return result
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error))
    except HTTPException:
        raise
    except Exception as error:
        raise HTTPException(status_code=500, detail=f"Paper Lab aktivasyon hatası: {_paper_lab_error(error)}")


@router.post("/auto-paper-lab")
def auto_paper_lab_models(current_user: dict = Depends(require_rule_owner)):
    user = catalog_owner_username()

    result = activate_paper_lab_rules(user, trigger="auto")
    new_models = result.get("models", []) or []
    new_model_ids = {item.get("model_id") for item in new_models if item.get("model_id")}

    data = load_shadow(user)
    lab = data.setdefault("paper_lab", {})
    existing_models = lab.setdefault("models", {})

    before_count = len(existing_models)
    removed_count = 0

    # Artık geçerli olmayan eski user_rule modellerini sil.
    for model_id in list(existing_models.keys()):
        model = existing_models.get(model_id) or {}

        is_custom_rule_model = (
            model.get("source") == "user_rule"
            or str(model_id).startswith("USER_FILTER_")
        )

        if is_custom_rule_model and model_id not in new_model_ids:
            existing_models.pop(model_id, None)
            removed_count += 1

    added_count = 0
    kept_count = 0

    for model in new_models:
        model_id = model.get("model_id")
        if not model_id:
            continue

        if model_id in existing_models:
            kept_count += 1
            existing = existing_models[model_id]

            # Geçmişi koru, sadece güncel rule tanımlarını ve isimleri yenile.
            existing["filter_id"] = model.get("filter_id")
            existing["strategy_id"] = model.get("strategy_id")
            existing["filter_name"] = model.get("filter_name")
            existing["strategy_name"] = model.get("strategy_name")
            existing["strategy_type"] = model.get("strategy_type")
            existing["compatibility"] = model.get("compatibility")
            existing["filter_rule"] = model.get("filter_rule")
            existing["strategy_rule"] = model.get("strategy_rule")
            existing["source"] = "user_rule"
            existing["status"] = "active"

            existing.setdefault("wallet_start", model.get("wallet_start", 1000))
            existing.setdefault("wallet_value", existing.get("wallet_start", 1000))
            existing.setdefault("slot_size", model.get("slot_size", 200))
            existing.setdefault("max_slots", model.get("max_slots", 5))
            existing.setdefault("max_open_positions", model.get("max_open_positions", 5))
            existing.setdefault("take_profit_percent", model.get("take_profit_percent", 1.5))
            existing.setdefault("stop_loss_percent", model.get("stop_loss_percent", 2.0))
            existing.setdefault("open_positions", [])
            existing.setdefault("history", [])

        else:
            model.setdefault("wallet_value", model.get("wallet_start", 1000))
            model.setdefault("open_positions", [])
            model.setdefault("history", [])
            model.setdefault("source", "user_rule")
            model.setdefault("status", "active")

            existing_models[model_id] = model
            added_count += 1

    lab["models"] = existing_models
    lab["custom_registry_count"] = len([
        item for item in existing_models.values()
        if item.get("source") == "user_rule"
    ])
    lab["last_auto_sync_at"] = result.get("activation", {}).get("time")
    lab["last_compatibility_logs"] = result.get("activation", {}).get("logs", [])[-200:]

    save_shadow(data, user)

    after_count = len(existing_models)

    return {
        "status": "ok",
        "mode": "auto_all_sync",
        "accepted_combinations": result.get("accepted_combinations", 0),
        "rejected_combinations": result.get("rejected_combinations", 0),
        "model_count": result.get("model_count", 0),
        "added_count": added_count,
        "kept_count": kept_count,
        "removed_count": removed_count,
        "before_count": before_count,
        "after_count": after_count,
        "activation": result.get("activation"),
    }



@router.get("/schema")
def rule_schema_contract(current_user: dict = Depends(require_rule_owner)):
    return build_rule_schema_contract()


@router.post("/schema/validate")
def validate_rule_schema_payload(payload: dict, current_user: dict = Depends(require_rule_owner)):
    rule = payload.get("rule") if isinstance(payload, dict) and "rule" in payload else payload
    return validate_rule_schema(rule)


@router.get("/governance")
def rule_governance(current_user: dict = Depends(require_rule_owner)):
    return build_rule_governance_report(current_username(current_user))


@router.get("/governance/final")
def rule_governance_final(current_user: dict = Depends(require_rule_owner)):
    return build_rule_final_governance_report(current_username(current_user))


@router.get("/lineage")
def rule_lineage(current_user: dict = Depends(require_rule_owner)):
    return build_rule_lineage_report(current_username(current_user))


@router.get("/impact")
def rule_impact(current_user: dict = Depends(require_rule_owner)):
    return build_rule_impact_report(current_username(current_user))


@router.post("/diff")
def rule_diff_payload(payload: dict, current_user: dict = Depends(require_rule_owner)):
    return build_rule_diff(current_username(current_user), payload.get("rule_id"), payload.get("candidate"))


@router.get("/export")
def export_rule_payload(current_user: dict = Depends(require_rule_owner)):
    return export_rules(current_username(current_user))


@router.post("/import")
def import_rule_payload(payload: dict, overwrite: bool = False, current_user: dict = Depends(require_rule_owner)):
    try:
        return import_rules(current_username(current_user), payload, overwrite=overwrite)
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error))




@router.get("/governance/schema-final")
def rule_governance_schema_final(current_user: dict = Depends(require_rule_owner)):
    return build_rule_governance_schema()


@router.get("/governance/evidence")
def rule_governance_evidence(current_user: dict = Depends(require_rule_owner)):
    return build_rule_governance_evidence(current_username(current_user))


@router.get("/governance/quality")
def rule_settings_governance_quality_from_rules(current_user: dict = Depends(require_rule_owner)):
    return build_rule_settings_governance_quality(current_username(current_user))


@router.get("/danger-warnings")
def rule_danger_warnings(rule_id: str | None = None, current_user: dict = Depends(require_rule_owner)):
    return build_rule_danger_warnings(current_username(current_user), rule_id=rule_id)


@router.post("/danger-warnings/preview")
def rule_danger_warnings_preview(payload: dict, current_user: dict = Depends(require_rule_owner)):
    candidate = payload.get("rule") if isinstance(payload, dict) and "rule" in payload else payload
    return build_rule_danger_warnings(current_username(current_user), candidate=candidate)


@router.get("/{rule_id}/lineage")
def rule_lineage_detail(rule_id: str, current_user: dict = Depends(require_rule_owner)):
    return build_rule_lineage_report(current_username(current_user), rule_id=rule_id)


@router.get("/{rule_id}/impact")
def rule_impact_detail(rule_id: str, current_user: dict = Depends(require_rule_owner)):
    return build_rule_impact_report(current_username(current_user), rule_id=rule_id)


@router.post("/{rule_id}/rollback-preview")
def rule_rollback_preview_payload(rule_id: str, payload: dict | None = None, current_user: dict = Depends(require_rule_owner)):
    payload = payload or {}
    return build_rule_rollback_preview(
        current_username(current_user),
        rule_id,
        archived_at=payload.get("archived_at"),
        version=payload.get("version"),
    )


@router.post("/{rule_id}/restore-version")
def restore_rule_version_payload(rule_id: str, payload: dict | None = None, current_user: dict = Depends(require_rule_owner)):
    payload = payload or {}
    try:
        result = restore_rule_version(
            current_username(current_user),
            rule_id,
            archived_at=payload.get("archived_at"),
            version=payload.get("version"),
        )
        user = current_username(current_user)
        data = load_shadow(user)
        append_audit(data, "rule.restore", "ok", f"Rule restore edildi: {rule_id}", meta={"category": "rule", "severity": "warning", "rule_id": rule_id, "endpoint": f"/api/rules/{rule_id}/restore-version", "role": current_user.get("role"), "after": result.get("restored")}, user=user)
        save_shadow(data, user)
        return result
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error))


@router.get("/{rule_id}/versions")
def rule_versions(rule_id: str, current_user: dict = Depends(require_rule_owner)):
    return get_rule_versions(current_username(current_user), rule_id)
