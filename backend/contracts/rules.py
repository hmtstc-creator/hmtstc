from __future__ import annotations

from typing import Any, Dict, Optional

from pydantic import BaseModel, Field


class RuleSaveRequest(BaseModel):
    rule: Dict[str, Any] = Field(default_factory=dict)
    reason: str = "manual_rule_save"
    trace_id: Optional[str] = None


class RuleDiffRequest(BaseModel):
    source_version: Optional[str] = None
    target_version: Optional[str] = None
    draft: Dict[str, Any] = Field(default_factory=dict)
