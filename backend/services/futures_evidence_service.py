from __future__ import annotations
from typing import Any, Dict
from services.binance_futures_models import now_iso
import hashlib, json

def build_futures_evidence(decision: Dict[str, Any]) -> Dict[str, Any]:
    payload={"created_at":now_iso(),"strategy_signal":decision.get("strategy_signal"),"filter_result":decision.get("filter_result"),"karabasan_score":decision.get("karabasan_score"),"futures_risk_score":decision.get("futures_risk_score"),"hard_blocks":decision.get("hard_blocks",[]),"order_preview":decision.get("order_preview"),"tp_sl":decision.get("tp_sl"),"leverage":decision.get("leverage"),"margin_type":decision.get("margin_type"),"liquidation_distance_pct":decision.get("liquidation_distance_pct"),"final_decision":decision.get("final_decision"),"order_sent":False}
    checksum=hashlib.sha256(json.dumps(payload, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
    return {"service":"futures_evidence_service","decision_id":decision.get("decision_id") or f"FUT-{checksum[:12]}","evidence":payload,"checksum":checksum,"immutable_policy":"Evidence yoksa canlı emir açılmaz.","admin_questions":["Neden açıldı?","Neden açılmadı?","Neden kapandı?","Hangi gate bloke etti?"]}
