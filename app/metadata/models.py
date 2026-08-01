from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional
from uuid import uuid4

from pydantic import BaseModel, Field, validator


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class Provenance(str, Enum):
    CV_EXTRACTED = "CV_EXTRACTED"
    USER_PROVIDED = "USER_PROVIDED"
    USER_CORRECTED = "USER_CORRECTED"
    INFERRED = "INFERRED"
    MISSING = "MISSING"
    CONFLICTING = "CONFLICTING"


class VerificationStatus(str, Enum):
    UNVERIFIED = "UNVERIFIED"
    VERIFIED = "VERIFIED"
    CONFLICTING = "CONFLICTING"
    NOT_APPLICABLE = "NOT_APPLICABLE"


class UserConfirmationStatus(str, Enum):
    PENDING = "PENDING"
    CONFIRMED = "CONFIRMED"
    REJECTED = "REJECTED"


class MetadataItem(BaseModel):
    item_id: str = Field(default_factory=lambda: str(uuid4()))
    category: str
    sub_category: Optional[str] = None
    normalized_value: str
    keywords: List[str] = Field(default_factory=list)
    original_text: Optional[str] = None
    source_page: Optional[int] = Field(default=None, ge=1)
    source_location: Optional[str] = None
    provenance: Provenance = Provenance.CV_EXTRACTED
    extraction_confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    verification_status: VerificationStatus = VerificationStatus.UNVERIFIED
    user_confirmation_status: UserConfirmationStatus = UserConfirmationStatus.PENDING
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)

    @validator("normalized_value")
    def value_must_not_be_empty(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("normalized_value must not be empty")
        return value


class PreferenceInformation(BaseModel):
    preferred_role: str = ""
    preparation_period: str = ""
    additional_information: str = ""


class RawExtraction(BaseModel):
    filename: str
    content_type: str
    byte_size: int = Field(ge=1)
    page_count: int = Field(default=0, ge=0)
    extracted_text: str = ""
    page_text: List[Dict[str, Any]] = Field(default_factory=list)
    extraction_method: str
    warnings: List[str] = Field(default_factory=list)


class NormalizedMetadata(BaseModel):
    items: List[MetadataItem] = Field(default_factory=list)
    preferences: PreferenceInformation = Field(default_factory=PreferenceInformation)
    warnings: List[str] = Field(default_factory=list)
    extraction_confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    normalization_method: str = "deterministic_section_normalizer"
    rephrasing_model: Optional[str] = None


class UserConfirmedMetadata(NormalizedMetadata):
    confirmed_at: Optional[datetime] = None
    revision: int = Field(default=0, ge=0)


class WorkflowState(BaseModel):
    request_id: str = Field(default_factory=lambda: str(uuid4()))
    workflow_id: str = Field(default_factory=lambda: str(uuid4()))
    status: str = "METADATA_REVIEW_REQUIRED"
    revision: int = Field(default=0, ge=0)
    pdf: RawExtraction
    normalized_metadata: NormalizedMetadata
    user_confirmed_metadata: Optional[UserConfirmedMetadata] = None
    errors: List[str] = Field(default_factory=list)
    warnings: List[str] = Field(default_factory=list)
    next_nodes: List[str] = Field(default_factory=list)
    interrupt_required: bool = False
    checkpointed: bool = False
    leading_agent: Dict[str, Any] = Field(default_factory=dict)
    claims: List[Dict[str, Any]] = Field(default_factory=list)
    evidence_ledger: Dict[str, Any] = Field(default_factory=lambda: {"claims": [], "evidence": [], "warnings": []})
    market_analysis: Dict[str, Any] = Field(default_factory=dict)
    supporting_findings: List[Dict[str, Any]] = Field(default_factory=list)
    judge_results: List[Dict[str, Any]] = Field(default_factory=list)
    readiness_classification: Optional[Dict[str, Any]] = None
    recommendations: List[Dict[str, Any]] = Field(default_factory=list)
    planner_result: Dict[str, Any] = Field(default_factory=dict)
    final_report: Dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)
