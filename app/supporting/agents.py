from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Dict, Iterable, List, Set

from app.evidence.models import ClaimType

from .models import (
    EvidenceState,
    FindingKind,
    SupportingAgentName,
    SupportingAgentRequest,
    SupportingAgentOutput,
    SupportingFinding,
)


class SupportingAgent(ABC):
    name: SupportingAgentName
    categories: Set[str]

    def run(self, request: SupportingAgentRequest) -> SupportingAgentOutput:
        try:
            findings = self._analyze(request)
            return SupportingAgentOutput(agent_name=self.name, findings=findings)
        except Exception as exc:
            return SupportingAgentOutput(
                agent_name=self.name,
                status="FAILED",
                errors=[f"Supporting agent failed safely: {exc.__class__.__name__}"],
                partial=True,
            )

    @abstractmethod
    def _analyze(self, request: SupportingAgentRequest) -> List[SupportingFinding]:
        raise NotImplementedError

    def _items(self, request: SupportingAgentRequest):
        return [item for item in request.user_confirmed_metadata.items if item.category in self.categories]

    def _related_references(self, request: SupportingAgentRequest):
        claims = request.claims
        evidence_ids = set(request.evidence_ids)
        for requirement in request.market_requirements:
            evidence_ids.update(requirement.get("evidence_ids", []))
        claim_ids = [claim.get("claim_id") for claim in claims if claim.get("claim_id")]
        return claim_ids, sorted(evidence_ids)

    def _finding_for_items(self, request: SupportingAgentRequest, title: str, category: str):
        items = self._items(request)
        claim_ids, evidence_ids = self._related_references(request)
        if items:
            return SupportingFinding(
                agent_name=self.name,
                category=category,
                kind=FindingKind.STRENGTH,
                title=title,
                analysis=f"Confirmed metadata contains {len(items)} item(s) in the {category} scope.",
                evidence_state=EvidenceState.PRESENT,
                metadata_item_ids=[item.item_id for item in items],
                claim_ids=claim_ids,
                evidence_ids=evidence_ids,
                confidence=0.7,
            )
        explicit_missing = any(item.provenance.value == "MISSING" for item in request.user_confirmed_metadata.items if item.category == category)
        return SupportingFinding(
            agent_name=self.name,
            category=category,
            kind=FindingKind.GAP,
            title=f"No confirmed {category} evidence",
            analysis=(
                "The confirmed profile explicitly marks this category as missing."
                if explicit_missing
                else "No confirmed metadata item was supplied for this category; absence is not treated as proof that the experience does not exist."
            ),
            evidence_state=EvidenceState.CONFIRMED_ABSENCE if explicit_missing else EvidenceState.MISSING,
            metadata_item_ids=[],
            claim_ids=claim_ids,
            evidence_ids=evidence_ids,
            confidence=0.8 if explicit_missing else 0.55,
        )


class ProjectCareerAgent(SupportingAgent):
    name = SupportingAgentName.PROJECT_CAREER
    categories = {"projects", "activities_and_career_experience", "internships", "research", "competitions"}

    def _analyze(self, request):
        return [self._finding_for_items(request, "Project and career evidence review", "project_career_experience")]


class LeadershipContributionAgent(SupportingAgent):
    name = SupportingAgentName.LEADERSHIP_CONTRIBUTION
    categories = {"leadership_and_contribution", "volunteering_and_contribution"}

    def _analyze(self, request):
        return [self._finding_for_items(request, "Leadership and contribution evidence review", "leadership_contribution")]


class LanguageCredentialAgent(SupportingAgent):
    name = SupportingAgentName.LANGUAGE_CREDENTIAL
    categories = {"language_proficiency", "certifications_and_credentials", "education_and_training", "technical_skills"}

    def _analyze(self, request):
        return [self._finding_for_items(request, "Language and credential evidence review", "language_credential")]


class CVPositioningAgent(SupportingAgent):
    name = SupportingAgentName.CV_POSITIONING
    categories = {"additional_information", "projects", "research", "activities_and_career_experience", "technical_skills"}

    def _analyze(self, request):
        return [self._finding_for_items(request, "CV positioning and expression evidence review", "cv_positioning_expression")]


AGENT_CLASSES = {
    agent.name: agent
    for agent in [
        ProjectCareerAgent(),
        LeadershipContributionAgent(),
        LanguageCredentialAgent(),
        CVPositioningAgent(),
    ]
}
