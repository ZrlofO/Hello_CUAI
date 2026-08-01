from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional
from uuid import uuid4

from pydantic import BaseModel, Field, validator

from app.metadata.models import UserConfirmedMetadata


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class SupportingAgentName(str, Enum):
    PROJECT_CAREER = "project_career_experience"
    LEADERSHIP_CONTRIBUTION = "leadership_contribution"
    LANGUAGE_CREDENTIAL = "language_credential"
    CV_POSITIONING = "cv_positioning_expression"


class EvidenceState(str, Enum):
    PRESENT = "PRESENT"
    MISSING = "MISSING"
    CONFIRMED_ABSENCE = "CONFIRMED_ABSENCE"
    UNCERTAIN = "UNCERTAIN"


class FindingKind(str, Enum):
    STRENGTH = "STRENGTH"
    GAP = "GAP"
    CONSISTENCY_ISSUE = "CONSISTENCY_ISSUE"
    EVIDENCE_LIMITATION = "EVIDENCE_LIMITATION"


class SupportingFinding(BaseModel):
    finding_id: str = Field(default_factory=lambda: f"find_{uuid4().hex}")
    agent_name: SupportingAgentName
    category: str
    kind: FindingKind
    title: str
    analysis: str
    evidence_state: EvidenceState
    metadata_item_ids: List[str] = Field(default_factory=list)
    claim_ids: List[str] = Field(default_factory=list)
    evidence_ids: List[str] = Field(default_factory=list)
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    unsupported_claim: bool = False

    @validator("title", "analysis")
    def required_content(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("finding title and analysis must not be empty")
        return value


class SupportingAgentRequest(BaseModel):
    user_confirmed_metadata: UserConfirmedMetadata
    preferred_role: str = ""
    preparation_period: str = ""
    selected_categories: List[str] = Field(default_factory=list)
    market_requirements: List[Dict[str, Any]] = Field(default_factory=list)
    claims: List[Dict[str, Any]] = Field(default_factory=list)
    evidence_ids: List[str] = Field(default_factory=list)
    max_workers: int = Field(default=4, ge=1, le=4)


class SupportingAgentOutput(BaseModel):
    agent_name: SupportingAgentName
    status: str = "COMPLETED"
    findings: List[SupportingFinding] = Field(default_factory=list)
    warnings: List[str] = Field(default_factory=list)
    errors: List[str] = Field(default_factory=list)
    partial: bool = False
    completed_at: datetime = Field(default_factory=utc_now)


class SupportingRunResponse(BaseModel):
    activated_agents: List[SupportingAgentName] = Field(default_factory=list)
    outputs: List[SupportingAgentOutput] = Field(default_factory=list)
    warnings: List[str] = Field(default_factory=list)
    errors: List[str] = Field(default_factory=list)
    partial: bool = False
    completed_at: datetime = Field(default_factory=utc_now)


class ConsultingReviewRequest(BaseModel):
    supporting_output: SupportingAgentOutput
    available_claims: List[Dict[str, Any]] = Field(default_factory=list)
    available_evidence_ids: List[str] = Field(default_factory=list)


class ConsultingReviewResponse(BaseModel):
    agent_name: SupportingAgentName
    outcome: str
    approved_finding_ids: List[str] = Field(default_factory=list)
    revision_finding_ids: List[str] = Field(default_factory=list)
    more_evidence_finding_ids: List[str] = Field(default_factory=list)
    unverifiable_finding_ids: List[str] = Field(default_factory=list)
    reasons: List[str] = Field(default_factory=list)
    reviewed_at: datetime = Field(default_factory=utc_now)
