from __future__ import annotations

from datetime import date
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

from .models import Claim, ClaimVerdict, Evidence, EvidenceStatus


class LedgerValidation(BaseModel):
    valid: bool
    errors: List[str] = Field(default_factory=list)
    warnings: List[str] = Field(default_factory=list)


class EvidenceLedger(BaseModel):
    claims: List[Claim] = Field(default_factory=list)
    evidence: List[Evidence] = Field(default_factory=list)
    warnings: List[str] = Field(default_factory=list)

    def claim_by_id(self, claim_id: str) -> Optional[Claim]:
        return next((claim for claim in self.claims if claim.claim_id == claim_id), None)

    def evidence_by_id(self, evidence_id: str) -> Optional[Evidence]:
        return next((item for item in self.evidence if item.evidence_id == evidence_id), None)

    def add_claim(self, claim: Claim) -> Claim:
        if self.claim_by_id(claim.claim_id):
            raise ValueError(f"Duplicate claim_id: {claim.claim_id}")
        self.claims.append(claim)
        return claim

    def add_evidence(self, evidence: Evidence) -> Evidence:
        if self.evidence_by_id(evidence.evidence_id):
            raise ValueError(f"Duplicate evidence_id: {evidence.evidence_id}")
        if evidence.claim_id and not self.claim_by_id(evidence.claim_id):
            raise ValueError(f"Unknown claim_id: {evidence.claim_id}")
        self.apply_deterministic_scores(evidence)
        self.evidence.append(evidence)
        return evidence

    @staticmethod
    def deterministic_source_quality(source_type: str) -> float:
        return {
            "OFFICIAL_COMPANY": 0.95,
            "OFFICIAL_INSTITUTION": 0.9,
            "GOVERNMENT": 0.95,
            "FIRST_PERSON": 0.7,
            "INTERVIEW": 0.75,
            "SECONDARY_SUMMARY": 0.5,
            "COMMUNITY": 0.25,
            "SEARCH_RESULT": 0.1,
            "USER_PROVIDED": 0.8,
            "UNKNOWN": 0.2,
        }.get(str(source_type), 0.2)

    @staticmethod
    def deterministic_freshness(publication_date: Optional[date], today: date) -> float:
        if not publication_date:
            return 0.0
        age_days = max(0, (today - publication_date).days)
        return round(max(0.0, 1.0 - min(age_days, 730) / 730), 3)

    @classmethod
    def apply_deterministic_scores(cls, evidence: Evidence, today: Optional[date] = None) -> Evidence:
        today = today or date.today()
        if evidence.source_quality_score == 0.0:
            evidence.source_quality_score = cls.deterministic_source_quality(evidence.source_type.value)
        if evidence.freshness_score == 0.0:
            evidence.freshness_score = cls.deterministic_freshness(evidence.publication_date, today)
        return evidence

    def attach_evidence(self, claim_id: str, evidence_id: str) -> Claim:
        claim = self.claim_by_id(claim_id)
        if not claim:
            raise ValueError(f"Unknown claim_id: {claim_id}")
        if not self.evidence_by_id(evidence_id):
            raise ValueError(f"Unknown evidence_id: {evidence_id}")
        if evidence_id not in claim.evidence_ids:
            claim.evidence_ids.append(evidence_id)
        claim.updated_at = claim.updated_at
        return claim

    def validate(self, today: Optional[date] = None) -> LedgerValidation:
        today = today or date.today()
        errors: List[str] = []
        warnings = list(self.warnings)
        claim_ids = {claim.claim_id for claim in self.claims}
        evidence_ids = {item.evidence_id for item in self.evidence}

        for claim in self.claims:
            missing = [item for item in claim.evidence_ids if item not in evidence_ids]
            if missing:
                errors.append(f"Claim {claim.claim_id} references unknown evidence: {', '.join(missing)}")
            if claim.external_verification_required and not claim.evidence_ids:
                warnings.append(f"Claim {claim.claim_id} requires evidence but has none; classified as UNVERIFIABLE")
                claim.current_verdict = ClaimVerdict.UNVERIFIABLE
            if claim.current_verdict in {ClaimVerdict.SUPPORTED, ClaimVerdict.PARTIALLY_SUPPORTED} and not claim.evidence_ids:
                errors.append(f"Claim {claim.claim_id} cannot be approved without evidence")

        for item in self.evidence:
            if item.claim_id and item.claim_id not in claim_ids:
                errors.append(f"Evidence {item.evidence_id} references unknown claim: {item.claim_id}")
            if item.publication_date and item.publication_date > today:
                warnings.append(f"Evidence {item.evidence_id} has a future publication date")
            if item.source_quality_score < 0.4:
                warnings.append(f"Evidence {item.evidence_id} has insufficient source quality")
            if not item.source_url and item.source_type.value != "USER_PROVIDED":
                warnings.append(f"Evidence {item.evidence_id} has no source URL and cannot provide external traceability")
            if item.publication_date is None and item.source_type.value != "USER_PROVIDED":
                warnings.append(f"Evidence {item.evidence_id} has no publication date; freshness is unknown")

        return LedgerValidation(valid=not errors, errors=errors, warnings=warnings)

    @classmethod
    def from_dict(cls, value: Optional[Dict[str, Any]]) -> "EvidenceLedger":
        return cls.model_validate(value or {})
