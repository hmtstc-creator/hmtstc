from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, Generic, List, Optional, TypeVar
from uuid import uuid4

from pydantic import BaseModel, Field


T = TypeVar("T")


class ApiMeta(BaseModel):
    trace_id: str = Field(default_factory=lambda: str(uuid4()))
    revision: int = 59
    generated_at: str = Field(default_factory=lambda: datetime.utcnow().isoformat(timespec="seconds") + "Z")


class ApiIssue(BaseModel):
    code: str
    message: str
    field: Optional[str] = None
    severity: str = "error"


class ApiEnvelope(BaseModel, Generic[T]):
    ok: bool = True
    status: str = "ok"
    data: Optional[T] = None
    errors: List[ApiIssue] = Field(default_factory=list)
    warnings: List[ApiIssue] = Field(default_factory=list)
    meta: ApiMeta = Field(default_factory=ApiMeta)


def envelope(data: Any = None, status: str = "ok", ok: bool | None = None, warnings: list | None = None) -> Dict[str, Any]:
    """Backward-compatible response envelope helper for new v2/admin contracts.

    Rev59 does not wrap existing v1 payloads automatically because the frontend
    already consumes their historical shapes. New contract-first endpoints and
    quality gates can use this helper without breaking legacy callers.
    """
    payload = ApiEnvelope[Any](
        ok=(status not in {"blocked", "error", "fail"} if ok is None else ok),
        status=status,
        data=data,
        warnings=warnings or [],
    )
    return payload.dict()
