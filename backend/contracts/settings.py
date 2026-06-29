from __future__ import annotations

from typing import Any, Dict, Optional

from pydantic import BaseModel, Field


class SettingsUpdateRequest(BaseModel):
    settings: Dict[str, Any] = Field(default_factory=dict)
    reason: str = "manual_settings_update"
    preview: bool = False
    trace_id: Optional[str] = None


class RiskProfileApplyRequest(BaseModel):
    profile: str
    reason: str = "manual_risk_profile_apply"
    trace_id: Optional[str] = None
