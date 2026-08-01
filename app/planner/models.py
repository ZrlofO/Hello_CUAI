from __future__ import annotations

from datetime import date, datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional
from uuid import uuid4

from pydantic import BaseModel, Field, validator


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class DateType(str, Enum):
    VERIFIED_EXTERNAL_DATE = "VERIFIED_EXTERNAL_DATE"
    PLANNER_SUGGESTED_DATE = "PLANNER_SUGGESTED_DATE"
    USER_CONFIRMED_DATE = "USER_CONFIRMED_DATE"
    UNSCHEDULED = "UNSCHEDULED"
    TENTATIVE = "TENTATIVE"


class TodoStatus(str, Enum):
    PROPOSED = "PROPOSED"
    READY = "READY"
    USER_CONFIRMATION_REQUIRED = "USER_CONFIRMATION_REQUIRED"
    BLOCKED = "BLOCKED"
    COMPLETED = "COMPLETED"


class TodoItem(BaseModel):
    task_id: str = Field(default_factory=lambda: f"task_{uuid4().hex}")
    category: str
    title: str
    reason: str
    related_gap: str = ""
    evidence_ids: List[str] = Field(default_factory=list)
    priority: str = "MEDIUM"
    estimated_effort: str = ""
    target_start_date: Optional[date] = None
    target_completion_date: Optional[date] = None
    external_deadline: Optional[date] = None
    date_type: DateType = DateType.UNSCHEDULED
    status: TodoStatus = TodoStatus.PROPOSED
    dependencies: List[str] = Field(default_factory=list)

    @validator("title", "reason")
    def required_text(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("todo title and reason must not be empty")
        return value


class CalendarProposal(BaseModel):
    proposal_id: str = Field(default_factory=lambda: f"cal_{uuid4().hex}")
    task_id: str
    title: str
    target_start_date: Optional[date] = None
    target_completion_date: Optional[date] = None
    external_deadline: Optional[date] = None
    date_type: DateType
    evidence_ids: List[str] = Field(default_factory=list)
    status: str = "PROPOSAL_ONLY"
    eligible_for_calendar: bool = False
    exclusion_reason: Optional[str] = None


class PlannerRequest(BaseModel):
    approved_finding_ids: List[str] = Field(default_factory=list)
    supporting_findings: List[Dict[str, Any]] = Field(default_factory=list)
    recommendation_candidates: List[Dict[str, Any]] = Field(default_factory=list)
    evidence: List[Dict[str, Any]] = Field(default_factory=list)
    preparation_period: str = ""
    user_confirmed_dates: Dict[str, Any] = Field(default_factory=dict)


class PlannerResponse(BaseModel):
    todo_items: List[TodoItem] = Field(default_factory=list)
    calendar_proposals: List[CalendarProposal] = Field(default_factory=list)
    warnings: List[str] = Field(default_factory=list)
    errors: List[str] = Field(default_factory=list)
    partial: bool = False
    calendar_write_enabled: bool = False
    generated_at: datetime = Field(default_factory=utc_now)
