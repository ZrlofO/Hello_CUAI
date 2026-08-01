from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from uuid import uuid4

from pydantic import BaseModel, Field

from app.metadata.models import UserConfirmedMetadata


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class ConsultingRequest(BaseModel):
    user_confirmed_metadata: UserConfirmedMetadata
    preferred_role: str = ""
    preparation_period: str = ""
    location: str = ""
    source_names: List[str] = Field(default_factory=list)
    max_companies: int = Field(default=10, ge=1, le=20)
    max_reference_cases: int = Field(default=20, ge=0, le=50)


class ScoreBreakdown(BaseModel):
    role_relevance: float = Field(ge=0.0, le=1.0)
    active_status: float = Field(ge=0.0, le=1.0)
    experience_match: float = Field(ge=0.0, le=1.0)
    skill_match: float = Field(ge=0.0, le=1.0)
    freshness: float = Field(ge=0.0, le=1.0)
    source_quality: float = Field(ge=0.0, le=1.0)
    deterministic_score: float = Field(ge=0.0, le=1.0)
    semantic_score: float = Field(ge=0.0, le=1.0)
    final_score: float = Field(ge=0.0, le=1.0)


class CompanyOpportunity(BaseModel):
    opportunity_id: str = Field(default_factory=lambda: f"opp_{uuid4().hex}")
    company_name: str
    title: str
    source_name: str
    source_url: str
    evidence_ids: List[str] = Field(default_factory=list)
    active_status: Optional[bool] = None
    publication_date: Optional[str] = None
    application_deadline: Optional[str] = None
    score: ScoreBreakdown
    selection_reasons: List[str] = Field(default_factory=list)


class MarketRequirement(BaseModel):
    requirement_id: str = Field(default_factory=lambda: f"req_{uuid4().hex}")
    requirement: str
    normalized_requirement: str
    requirement_type: str = "skill_or_qualification"
    company_count: int = Field(ge=1)
    company_ids: List[str] = Field(default_factory=list)
    evidence_ids: List[str] = Field(default_factory=list)
    common_requirement: bool = False
    company_specific: bool = False


class ReferenceCasePolicy(BaseModel):
    max_reference_cases: int = Field(default=20, ge=0, le=50)
    status: str = "INTERFACE_RESERVED"
    accepted_case_implementation: bool = False
    warning: str = "Accepted-candidate cases are not retrieved or asserted in Phase 5."


class ConsultingResponse(BaseModel):
    target_role: str
    preparation_period: str
    companies: List[CompanyOpportunity] = Field(default_factory=list)
    market_requirements: List[MarketRequirement] = Field(default_factory=list)
    claims: List[Dict[str, Any]] = Field(default_factory=list)
    evidence_ids: List[str] = Field(default_factory=list)
    reference_case_policy: ReferenceCasePolicy
    warnings: List[str] = Field(default_factory=list)
    errors: List[str] = Field(default_factory=list)
    partial: bool = False
    completed_at: datetime = Field(default_factory=utc_now)
