from __future__ import annotations

from typing import Any, Dict, Optional

from pydantic import BaseModel, Field


class IdempotentCommand(BaseModel):
    command_id: Optional[str] = Field(default=None, description="Client-side command id for audit/debug correlation.")
    idempotency_key: Optional[str] = Field(default=None, description="Stable key to prevent duplicated money-moving actions.")
    trace_id: Optional[str] = Field(default=None, description="End-to-end request trace id.")


class OrderPreviewRequest(IdempotentCommand):
    symbol: str = "BTCUSDT"
    side: str = "BUY"
    quantity: Optional[float] = None
    quote_amount: Optional[float] = None
    order_type: str = "MARKET"
    meta: Dict[str, Any] = Field(default_factory=dict)


class OrderPlaceRequest(OrderPreviewRequest):
    owner_confirmed: bool = False
    preview_token: Optional[str] = None


class PositionTransitionRequest(IdempotentCommand):
    position_id: str
    to_status: str
    reason: str = "manual_ui_transition"
    meta: Dict[str, Any] = Field(default_factory=dict)
