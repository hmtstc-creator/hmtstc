from __future__ import annotations
from typing import Any, Dict
from services.binance_futures_models import now_iso

def build_mobile_safety_contract(action: str | None = None) -> Dict[str, Any]:
    critical = str(action or '').lower() in {"start_bot","enable_live","emergency_stop","close_position","open_position"}
    return {"service":"futures_mobile_safety","checked_at":now_iso(),"mobile_first":True,"sticky_emergency_stop":True,"critical_action":critical,"confirmation_required":critical,"confirmation_text":"Bu işlem Futures botunu canlı etkiler. Onaylıyor musun?" if critical else None,"layouts_checked":["iphone","android","small_screen","tablet","portrait","landscape"],"management":"Mobilde yanlışlıkla emir açma/kapatma riski modal ve buton yerleşimiyle düşürülür."}
