from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from uuid import uuid4

from pydantic import BaseModel, Field


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class FinalReport(BaseModel):
    report_id: str = Field(default_factory=lambda: f"report_{uuid4().hex}")
    request_id: str
    workflow_id: str
    status: str
    summary: Dict[str, Any] = Field(default_factory=dict)
    profile_summary: Dict[str, Any] = Field(default_factory=dict)
    market_analysis: Dict[str, Any] = Field(default_factory=dict)
    strengths: List[Dict[str, Any]] = Field(default_factory=list)
    weaknesses: List[Dict[str, Any]] = Field(default_factory=list)
    supporting_findings: List[Dict[str, Any]] = Field(default_factory=list)
    readiness_classification: Optional[Dict[str, Any]] = None
    recommendations: List[Dict[str, Any]] = Field(default_factory=list)
    planner_result: Dict[str, Any] = Field(default_factory=dict)
    calendar_proposals: List[Dict[str, Any]] = Field(default_factory=list)
    todo_items: List[Dict[str, Any]] = Field(default_factory=list)
    citations: List[Dict[str, Any]] = Field(default_factory=list)
    uncertainty_notes: List[str] = Field(default_factory=list)
    warnings: List[str] = Field(default_factory=list)
    errors: List[str] = Field(default_factory=list)
    graph_status: Dict[str, Any] = Field(default_factory=dict)
    generated_at: datetime = Field(default_factory=utc_now)
