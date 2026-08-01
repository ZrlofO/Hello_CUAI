from __future__ import annotations

from datetime import date, datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional
from uuid import uuid4

from pydantic import BaseModel, Field, validator


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class ClaimType(str, Enum):
    USER_FACT = "user_fact"
    EXTRACTED_CV_FACT = "extracted_cv_fact"
    USER_CORRECTED_FACT = "user_corrected_fact"
    MARKET_FACT = "market_fact"
    JOB_POSTING_FACT = "job_posting_fact"
    DEADLINE_FACT = "deadline_fact"
    ACCEPTED_CANDIDATE_CASE = "accepted_candidate_case"
    AGENT_INFERENCE = "agent_inference"
    GAP_ASSESSMENT = "gap_assessment"
    RECOMMENDATION = "recommendation"
    SCHEDULING_FACT = "scheduling_fact"
    FINAL_REPORT_STATEMENT = "final_report_statement"


class ClaimVerdict(str, Enum):
    PENDING = "PENDING"
    SUPPORTED = "SUPPORTED"
    PARTIALLY_SUPPORTED = "PARTIALLY_SUPPORTED"
    CONTRADICTED = "CONTRADICTED"
    UNVERIFIABLE = "UNVERIFIABLE"
    AMBIGUOUS = "AMBIGUOUS"
    STALE_EVIDENCE = "STALE_EVIDENCE"
    SOURCE_QUALITY_INSUFFICIENT = "SOURCE_QUALITY_INSUFFICIENT"
    NOT_APPLICABLE = "NOT_APPLICABLE"


class EvidenceStatus(str, Enum):
    UNVERIFIED = "UNVERIFIED"
    VERIFIED = "VERIFIED"
    SUPPORTS = "SUPPORTS"
    CONTRADICTS = "CONTRADICTS"
    REJECTED = "REJECTED"


class SourceType(str, Enum):
    OFFICIAL_COMPANY = "OFFICIAL_COMPANY"
    OFFICIAL_INSTITUTION = "OFFICIAL_INSTITUTION"
    GOVERNMENT = "GOVERNMENT"
    FIRST_PERSON = "FIRST_PERSON"
    INTERVIEW = "INTERVIEW"
    SECONDARY_SUMMARY = "SECONDARY_SUMMARY"
    COMMUNITY = "COMMUNITY"
    SEARCH_RESULT = "SEARCH_RESULT"
    USER_PROVIDED = "USER_PROVIDED"
    UNKNOWN = "UNKNOWN"


class Claim(BaseModel):
    claim_id: str = Field(default_factory=lambda: f"clm_{uuid4().hex}")
    claim_text: str
    claim_type: ClaimType
    subject: Optional[str] = None
    predicate: Optional[str] = None
    object_or_value: Optional[Any] = None
    produced_by: str
    metadata_references: List[str] = Field(default_factory=list)
    evidence_ids: List[str] = Field(default_factory=list)
    importance: str = "medium"
    external_verification_required: bool = False
    current_verdict: ClaimVerdict = ClaimVerdict.PENDING
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    review_history: List[Dict[str, Any]] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)

    @validator("claim_text", "produced_by")
    def required_text(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("claim text and produced_by must not be empty")
        return value

    @validator("importance")
    def valid_importance(cls, value: str) -> str:
        value = value.lower().strip()
        if value not in {"low", "medium", "high", "critical"}:
            raise ValueError("importance must be low, medium, high, or critical")
        return value


class Evidence(BaseModel):
    evidence_id: str = Field(default_factory=lambda: f"evd_{uuid4().hex}")
    claim_id: Optional[str] = None
    source_type: SourceType = SourceType.UNKNOWN
    source_url: Optional[str] = None
    source_title: Optional[str] = None
    publisher: Optional[str] = None
    publication_date: Optional[date] = None
    retrieval_date: date = Field(default_factory=date.today)
    application_deadline: Optional[date] = None
    active_status_verified: Optional[bool] = None
    relevant_excerpt: Optional[str] = None
    normalized_fact: Optional[str] = None
    source_quality_score: float = Field(default=0.0, ge=0.0, le=1.0)
    freshness_score: float = Field(default=0.0, ge=0.0, le=1.0)
    relevance_score: float = Field(default=0.0, ge=0.0, le=1.0)
    support_status: EvidenceStatus = EvidenceStatus.UNVERIFIED
    retrieval_query: Optional[str] = None
    retrieved_by_node: Optional[str] = None
    verification_status: EvidenceStatus = EvidenceStatus.UNVERIFIED
    rejection_reason: Optional[str] = None
    created_at: datetime = Field(default_factory=utc_now)

    @validator("source_url")
    def valid_url(cls, value: Optional[str]) -> Optional[str]:
        if value and not value.lower().startswith(("http://", "https://")):
            raise ValueError("source_url must be an http(s) URL")
        return value

