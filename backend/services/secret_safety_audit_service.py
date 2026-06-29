from __future__ import annotations
from typing import Any, Dict
from services.binance_futures_models import now_iso
SENSITIVE_KEYS = ["secret", "api_secret", "futures_secret", "withdraw"]

def build_secret_safety_audit(payload: Dict[str, Any] | None = None) -> Dict[str, Any]:
    payload=payload or {}
    exposed=[k for k,v in payload.items() if any(s in k.lower() for s in SENSITIVE_KEYS) and v]
    return {"service":"secret_safety_audit","checked_at":now_iso(),"secret_keys_detected":exposed,"frontend_secret_return_allowed":False,"log_secret_allowed":False,"status":"blocked" if exposed else "ok","management":"Secret frontend’e veya loglara düşerse production live gate kapalı kalır."}
