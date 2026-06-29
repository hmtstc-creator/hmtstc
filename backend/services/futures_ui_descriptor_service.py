from __future__ import annotations
from typing import Dict, Any
from services.binance_futures_models import now_iso

def build_futures_ui_descriptor(is_owner: bool=False) -> Dict[str, Any]:
    user_cards=["API durumu","Bot durumu","Futures izin durumu","Açık pozisyon","Net PnL","Risk kartı","Karabasan Futures skoru","Basit işlem logları"]
    admin_cards=["Kullanıcı listesi","Yetki durumu","Risk durumu","Karabasan skor kırılımı","Lifecycle logları","Ledger","Owner gelir paneli"]
    return {"service":"futures_ui_descriptor","checked_at":now_iso(),"role":"owner" if is_owner else "user","visible_cards": admin_cards if is_owner else user_cards,"hidden_for_unauthorized":True,"risk_colors":{"safe":"green","warning":"yellow","blocked":"red"},"management":"Kullanıcı sade ekran, owner/admin analitik ekran görür."}
