from __future__ import annotations

from datetime import date, datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional
from uuid import uuid4

from pydantic import BaseModel, Field

from app.planner.models import CalendarProposal, DateType


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class AuthorizationStatus(str, Enum):
    NOT_CONFIGURED = "NOT_CONFIGURED"
    USER_APPROVAL_REQUIRED = "USER_APPROVAL_REQUIRED"
    USER_APPROVED = "USER_APPROVED"
    USER_DENIED = "USER_DENIED"


class CalendarProposalApproval(BaseModel):
    proposal_id: str
    approved: bool = False
    user_confirmed_start: Optional[date] = None
    user_confirmed_end: Optional[date] = None


class CalendarBatchRequest(BaseModel):
    authorization_status: AuthorizationStatus = AuthorizationStatus.USER_APPROVAL_REQUIRED
    proposals: List[CalendarProposal] = Field(default_factory=list)
    approvals: List[CalendarProposalApproval] = Field(default_factory=list)
    evidence: List[Dict[str, Any]] = Field(default_factory=list)
    mock_mode: bool = True


class CalendarWriteResult(BaseModel):
    result_id: str = Field(default_factory=lambda: f"cal_result_{uuid4().hex}")
    proposal_id: str
    status: str
    event_id: Optional[str] = None
    error_code: Optional[str] = None
    message: str = ""
    external_write_performed: bool = False


class CalendarBatchResponse(BaseModel):
    results: List[CalendarWriteResult] = Field(default_factory=list)
    warnings: List[str] = Field(default_factory=list)
    errors: List[str] = Field(default_factory=list)
    partial: bool = False
    external_write_performed: bool = False
    provider: str = "mock"
    generated_at: datetime = Field(default_factory=utc_now)
