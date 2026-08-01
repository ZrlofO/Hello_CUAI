from __future__ import annotations

import os
import re
from collections import Counter, defaultdict
from datetime import date
from typing import Callable, Dict, Iterable, List, Optional, Set, Tuple

from app.evidence.ledger import EvidenceLedger
from app.evidence.models import Claim, ClaimType, ClaimVerdict, Evidence, EvidenceStatus
from app.metadata.models import UserConfirmedMetadata
from app.retrieval.models import RetrievalRequest, RetrievalResponse, RetrievedPage
from app.retrieval.pipeline import RetrievalPipeline

from .models import (
    CompanyOpportunity,
    ConsultingRequest,
    ConsultingResponse,
    MarketRequirement,
    ReferenceCasePolicy,
    ScoreBreakdown,
)


TOKEN_PATTERN = re.compile(r"[A-Za-z][A-Za-z0-9+#.-]{1,}|[가-힣]{2,}")
STOPWORDS = {"and", "the", "for", "with", "required", "requirements", "경험", "및", "관련", "채용"}
REQUIREMENT_PATTERNS = (
    re.compile(r"(?:required skills?|requirements?|자격요건|필수 역량|주요 기술)\s*[:：]?\s*([^.;|]+)", re.I),
    re.compile(r"(?:experience with|proficiency in|경험 우대|사용 기술)\s*[:：]?\s*([^.;|]+)", re.I),
)


def tokens(value: str) -> Set[str]:
    return {
        token.lower()
        for token in TOKEN_PATTERN.findall(value or "")
        if token.lower() not in STOPWORDS and len(token) > 1
    }


def overlap_score(left: Set[str], right: Set[str]) -> float:
    if not left or not right:
        return 0.0
    return round(len(left & right) / max(1, len(left)), 3)


SemanticRanker = Callable[[str, str], float]


class ConsultingAgent:
    def __init__(
        self,
        retrieval_pipeline: RetrievalPipeline,
        semantic_ranker: Optional[SemanticRanker] = None,
        ledger: Optional[EvidenceLedger] = None,
    ):
        self.retrieval_pipeline = retrieval_pipeline
        self.semantic_ranker = semantic_ranker
        self.ledger = ledger or EvidenceLedger()
        self.deterministic_weight = float(os.getenv("CONSULTING_DETERMINISTIC_WEIGHT", "0.8"))
        self.semantic_weight = float(os.getenv("CONSULTING_SEMANTIC_WEIGHT", "0.2"))

    def analyze(self, request: ConsultingRequest) -> Tuple[ConsultingResponse, EvidenceLedger]:
        metadata = request.user_confirmed_metadata
        role = request.preferred_role.strip() or metadata.preferences.preferred_role.strip()
        period = request.preparation_period.strip() or metadata.preferences.preparation_period.strip()
        response = ConsultingResponse(
            target_role=role,
            preparation_period=period,
            reference_case_policy=ReferenceCasePolicy(max_reference_cases=request.max_reference_cases),
        )
        if not role:
            response.warnings.append("Preferred role is missing; role relevance scores are zero")

        retrieval_request = RetrievalRequest(
            intent=f"current hiring requirements for {role or 'the target role'}",
            target_role=role,
            location=request.location,
            preparation_period=period,
            limit=request.max_companies,
            source_names=request.source_names,
        )
        try:
            retrieval_response, self.ledger = self.retrieval_pipeline.run(retrieval_request, self.ledger)
        except Exception as exc:
            response.errors.append(f"Retrieval failed safely: {exc.__class__.__name__}")
            response.partial = True
            return response, self.ledger

        response.warnings.extend(retrieval_response.warnings)
        response.errors.extend(retrieval_response.errors)
        response.partial = bool(retrieval_response.errors or retrieval_response.warnings)
        response.companies = self._score_companies(request, retrieval_response)
        response.market_requirements = self._extract_requirements(response.companies, retrieval_response)
        self._create_claims(response, retrieval_response)
        response.claims = [claim.model_dump(mode="json") for claim in self.ledger.claims]
        response.evidence_ids = [item.evidence_id for item in self.ledger.evidence if item.verification_status != EvidenceStatus.REJECTED]
        if not response.companies:
            response.warnings.append("No valid active or evidence-backed company opportunities were found")
            response.partial = True
        return response, self.ledger

    def _score_companies(self, request: ConsultingRequest, retrieval: RetrievalResponse) -> List[CompanyOpportunity]:
        metadata_text = " ".join(item.normalized_value for item in request.user_confirmed_metadata.items)
        skill_text = " ".join(
            item.normalized_value
            for item in request.user_confirmed_metadata.items
            if item.category in {"technical_skills", "projects", "research", "certifications_and_credentials"}
        )
        role_tokens = tokens(request.preferred_role or request.user_confirmed_metadata.preferences.preferred_role)
        experience_tokens = tokens(metadata_text)
        skill_tokens = tokens(skill_text)
        evidence_by_url = {item.source_url: item for item in self.ledger.evidence if item.source_url}
        pages_by_url = {page.url: page for page in retrieval.pages}
        scored: List[CompanyOpportunity] = []
        for result in retrieval.search_results:
            page = pages_by_url.get(result.url)
            evidence = evidence_by_url.get(result.url)
            if not page or page.retrieval_error or page.restricted or not evidence:
                continue
            if evidence.verification_status == EvidenceStatus.REJECTED:
                continue
            text = " ".join([result.title, result.snippet, page.relevant_passage])
            role_relevance = overlap_score(role_tokens, tokens(text))
            active_status = 1.0 if page.active_status is True else 0.0 if page.active_status is False else 0.25
            experience_match = overlap_score(experience_tokens, tokens(text))
            skill_match = overlap_score(skill_tokens, tokens(text))
            freshness = evidence.freshness_score
            source_quality = evidence.source_quality_score
            deterministic = round(
                0.30 * role_relevance
                + 0.20 * active_status
                + 0.15 * experience_match
                + 0.15 * skill_match
                + 0.10 * freshness
                + 0.10 * source_quality,
                3,
            )
            semantic = 0.0
            if self.semantic_ranker:
                try:
                    semantic = min(max(float(self.semantic_ranker(request.preferred_role, text)), 0.0), 1.0)
                except Exception:
                    semantic = 0.0
            final = round(self.deterministic_weight * deterministic + self.semantic_weight * semantic, 3)
            scored.append(
                CompanyOpportunity(
                    company_name=evidence.publisher or result.publisher or "Unknown company",
                    title=result.title,
                    source_name=result.source_name,
                    source_url=result.url,
                    evidence_ids=[evidence.evidence_id],
                    active_status=page.active_status,
                    publication_date=page.publication_date.isoformat() if page.publication_date else None,
                    application_deadline=page.application_deadline.isoformat() if page.application_deadline else None,
                    score=ScoreBreakdown(
                        role_relevance=role_relevance,
                        active_status=active_status,
                        experience_match=experience_match,
                        skill_match=skill_match,
                        freshness=freshness,
                        source_quality=source_quality,
                        deterministic_score=deterministic,
                        semantic_score=semantic,
                        final_score=final,
                    ),
                    selection_reasons=[
                        "role relevance scored",
                        "active status evaluated",
                        "profile and skill overlap scored",
                        "freshness and source quality evaluated",
                    ],
                )
            )
        return sorted(scored, key=lambda item: item.score.final_score, reverse=True)[:request.max_companies]

    def _extract_requirements(self, companies: List[CompanyOpportunity], retrieval: RetrievalResponse) -> List[MarketRequirement]:
        pages = {page.url: page for page in retrieval.pages}
        occurrences: Dict[str, Set[str]] = defaultdict(set)
        evidence_refs: Dict[str, Set[str]] = defaultdict(set)
        for company in companies:
            page = pages.get(company.source_url)
            text = page.relevant_passage if page else ""
            matches: List[str] = []
            for pattern in REQUIREMENT_PATTERNS:
                matches.extend(pattern.findall(text))
            if not matches:
                matches = [part.strip() for part in re.split(r"[,/|·]", text) if 2 <= len(part.strip()) <= 60]
            for match in matches:
                normalized = re.sub(r"\s+", " ", match).strip(" .:-")
                if not normalized:
                    continue
                key = normalized.lower()
                occurrences[key].add(company.opportunity_id)
                evidence_refs[key].update(company.evidence_ids)
        requirement_count = len(companies)
        requirements = []
        for key, company_ids in occurrences.items():
            common = len(company_ids) >= max(2, (requirement_count + 1) // 2)
            requirements.append(
                MarketRequirement(
                    requirement=key,
                    normalized_requirement=key,
                    company_count=len(company_ids),
                    company_ids=list(company_ids),
                    evidence_ids=list(evidence_refs[key]),
                    common_requirement=common,
                    company_specific=not common,
                )
            )
        return sorted(requirements, key=lambda item: (item.common_requirement, item.company_count), reverse=True)

    def _create_claims(self, response: ConsultingResponse, retrieval: RetrievalResponse) -> None:
        for company in response.companies:
            claim = Claim(
                claim_text=f"{company.company_name} has a retrieved job posting titled '{company.title}'.",
                claim_type=ClaimType.JOB_POSTING_FACT,
                subject=company.company_name,
                predicate="has_retrieved_job_posting",
                object_or_value=company.title,
                produced_by="consulting_agent",
                evidence_ids=list(company.evidence_ids),
                importance="high",
                external_verification_required=True,
                current_verdict=ClaimVerdict.PENDING,
                confidence=company.score.final_score,
            )
            self.ledger.add_claim(claim)
        for requirement in response.market_requirements:
            claim = Claim(
                claim_text=f"'{requirement.requirement}' appears in retrieved market material.",
                claim_type=ClaimType.MARKET_FACT,
                subject=requirement.requirement,
                predicate="appears_in_market_material",
                object_or_value=requirement.company_count,
                produced_by="consulting_agent",
                evidence_ids=list(requirement.evidence_ids),
                importance="medium",
                external_verification_required=True,
                current_verdict=ClaimVerdict.PENDING,
                confidence=min(1.0, requirement.company_count / max(1, len(response.companies))),
            )
            self.ledger.add_claim(claim)
