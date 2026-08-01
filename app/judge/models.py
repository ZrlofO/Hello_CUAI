from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional
from uuid import uuid4

from pydantic import BaseModel, Field


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class JudgeVerdict(str, Enum):
    SUPPORTED = "SUPPORTED"
    PARTIALLY_SUPPORTED = "PARTIALLY_SUPPORTED"
    CONTRADICTED = "CONTRADICTED"
    UNVERIFIABLE = "UNVERIFIABLE"
    AMBIGUOUS = "AMBIGUOUS"
    STALE_EVIDENCE = "STALE_EVIDENCE"
    SOURCE_QUALITY_INSUFFICIENT = "SOURCE_QUALITY_INSUFFICIENT"


class RoutingDecision(str, Enum):
    APPROVED = "APPROVED"
    REVISION_REQUIRED = "REVISION_REQUIRED"
    MORE_EVIDENCE_REQUIRED = "MORE_EVIDENCE_REQUIRED"
    ESCALATE_TO_JUDGE = "ESCALATE_TO_JUDGE"
    UNVERIFIABLE = "UNVERIFIABLE"


class JudgeEvidenceInput(BaseModel):
    evidence_id: str
    claim_id: Optional[str] = None
    source_url: Optional[str] = None
    source_title: Optional[str] = None
    relevant_excerpt: Optional[str] = None
    normalized_fact: Optional[str] = None
    publication_date: Optional[str] = None
    application_deadline: Optional[str] = None
    active_status_verified: Optional[bool] = None
    source_quality_score: float = Field(default=0.0, ge=0.0, le=1.0)
    freshness_score: float = Field(default=0.0, ge=0.0, le=1.0)
    relevance_score: float = Field(default=0.0, ge=0.0, le=1.0)
    support_status: str = "UNVERIFIED"
    verification_status: str = "UNVERIFIED"


class JudgeClaimInput(BaseModel):
    claim_id: str
    claim_text: str
    claim_type: str
    evidence_ids: List[str] = Field(default_factory=list)
    external_verification_required: bool = False
    importance: str = "medium"


class JudgeRequest(BaseModel):
    supplied_metadata: Dict[str, Any] = Field(default_factory=dict)
    claims: List[JudgeClaimInput] = Field(default_factory=list)
    evidence: List[JudgeEvidenceInput] = Field(default_factory=list)
    max_debate_rounds: int = Field(default=3, ge=1, le=5)
    max_retries: int = Field(default=2, ge=0, le=5)


class JudgeEvaluation(BaseModel):
    evaluation_id: str = Field(default_factory=lambda: f"eval_{uuid4().hex}")
    claim_id: str
    verdict: JudgeVerdict
    evidence_used_ids: List[str] = Field(default_factory=list)
    contradicting_evidence_ids: List[str] = Field(default_factory=list)
    evidence_status: str
    source_quality: float = Field(default=0.0, ge=0.0, le=1.0)
    freshness: float = Field(default=0.0, ge=0.0, le=1.0)
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    reason: str
    required_next_action: RoutingDecision
    judge_mode: str = "deterministic"
    debate_round: int = 0
    retry_count: int = 0
    created_at: datetime = Field(default_factory=utc_now)


class AdaptiveDebateConfig(BaseModel):
    max_debate_rounds: int = Field(default=3, ge=1, le=5)
    max_retries: int = Field(default=2, ge=0, le=5)
    minimum_source_quality: float = Field(default=0.4, ge=0.0, le=1.0)
    minimum_freshness: float = Field(default=0.25, ge=0.0, le=1.0)


class DebateResponse(BaseModel):
    evaluations: List[JudgeEvaluation] = Field(default_factory=list)
    routing: Dict[str, RoutingDecision] = Field(default_factory=dict)
    retry_counts: Dict[str, int] = Field(default_factory=dict)
    debate_round: int = 0
    partial: bool = False
    warnings: List[str] = Field(default_factory=list)
    errors: List[str] = Field(default_factory=list)
