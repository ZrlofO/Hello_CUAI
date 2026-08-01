from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List
from uuid import uuid4

from pydantic import BaseModel, Field

from app.metadata.models import UserConfirmedMetadata


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class ReadinessLabel(str, Enum):
    STABLE = "Stable"
    APPROPRIATE = "Appropriate"
    RISK = "Risk"


class ReadinessIndicators(BaseModel):
    target_role_requirement_coverage: float = Field(default=0.0, ge=0.0, le=1.0)
    critical_gap_count: int = Field(default=0, ge=0)
    evidence_backed_experience_strength: float = Field(default=0.0, ge=0.0, le=1.0)
    preparation_period_feasibility: float = Field(default=0.0, ge=0.0, le=1.0)
    credential_requirement_coverage: float = Field(default=0.0, ge=0.0, le=1.0)
    unresolved_claim_count: int = Field(default=0, ge=0)
    stale_or_low_quality_evidence_count: int = Field(default=0, ge=0)
    contradictory_claim_count: int = Field(default=0, ge=0)
    approved_claim_count: int = Field(default=0, ge=0)
    total_requirement_count: int = Field(default=0, ge=0)


class ReadinessRequest(BaseModel):
    user_confirmed_metadata: UserConfirmedMetadata
    preferred_role: str = ""
    preparation_period: str = ""
    market_requirements: List[Dict[str, Any]] = Field(default_factory=list)
    claims: List[Dict[str, Any]] = Field(default_factory=list)
    evidence: List[Dict[str, Any]] = Field(default_factory=list)
    supporting_findings: List[Dict[str, Any]] = Field(default_factory=list)
    judge_evaluations: List[Dict[str, Any]] = Field(default_factory=list)


class ReadinessResponse(BaseModel):
    classification_id: str = Field(default_factory=lambda: f"ready_{uuid4().hex}")
    label: ReadinessLabel
    confidence: float = Field(ge=0.0, le=1.0)
    indicators: ReadinessIndicators
    policy_version: str = "readiness-v1"
    reasons: List[str] = Field(default_factory=list)
    limitations: List[str] = Field(default_factory=list)
    disclaimer: str = "This is a conservative career-readiness estimate, not an employment or acceptance guarantee."
    generated_at: datetime = Field(default_factory=utc_now)
