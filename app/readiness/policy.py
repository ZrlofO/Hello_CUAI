from __future__ import annotations

import re
from typing import Any, Dict, Iterable, List, Set

from app.judge.models import JudgeVerdict

from .models import ReadinessIndicators, ReadinessLabel, ReadinessRequest, ReadinessResponse


TOKEN_PATTERN = re.compile(r"[A-Za-z][A-Za-z0-9+#.-]{1,}|[가-힣]{2,}")
STOPWORDS = {"and", "the", "for", "with", "required", "requirements", "경험", "및", "관련", "채용"}
CRITICAL_REQUIREMENT_TYPES = {"credential", "qualification", "certification", "education"}


def _tokens(value: str) -> Set[str]:
    return {
        token.lower()
        for token in TOKEN_PATTERN.findall(value or "")
        if token.lower() not in STOPWORDS and len(token) > 1
    }


def _overlap(left: Set[str], right: Set[str]) -> float:
    if not left or not right:
        return 0.0
    return len(left & right) / max(1, len(left))


def _as_float(value: Any, default: float = 0.0) -> float:
    try:
        return min(max(float(value), 0.0), 1.0)
    except (TypeError, ValueError):
        return default


def _preparation_feasibility(period: str, gap_count: int) -> float:
    text = (period or "").lower()
    match = re.search(r"(\d+(?:\.\d+)?)\s*(month|months|개월|주|week|weeks|일|day|days)", text)
    if not match:
        return 0.25
    amount = float(match.group(1))
    unit = match.group(2)
    months = amount / 4.0 if unit in {"주", "week", "weeks"} else amount / 30.0 if unit in {"일", "day", "days"} else amount
    if gap_count == 0:
        return 1.0
    if months >= 6:
        return 0.9
    if months >= 3:
        return 0.75 if gap_count <= 3 else 0.55
    if months >= 1:
        return 0.55 if gap_count <= 2 else 0.3
    return 0.2


class ReadinessPolicy:
    def __init__(self, minimum_source_quality: float = 0.4, minimum_freshness: float = 0.25):
        self.minimum_source_quality = minimum_source_quality
        self.minimum_freshness = minimum_freshness

    def classify(self, request: ReadinessRequest) -> ReadinessResponse:
        metadata_text = " ".join(item.normalized_value for item in request.user_confirmed_metadata.items)
        metadata_tokens = _tokens(metadata_text)
        requirements = request.market_requirements
        covered = 0
        credential_total = 0
        credential_covered = 0
        for requirement in requirements:
            requirement_text = str(requirement.get("normalized_requirement") or requirement.get("requirement") or "")
            requirement_tokens = _tokens(requirement_text)
            is_covered = _overlap(requirement_tokens, metadata_tokens) >= 0.5
            if is_covered:
                covered += 1
            kind = str(requirement.get("requirement_type", "")).lower()
            if kind in CRITICAL_REQUIREMENT_TYPES or any(term in requirement_text.lower() for term in ["certif", "credential", "자격", "학력", "degree"]):
                credential_total += 1
                if is_covered:
                    credential_covered += 1

        findings = request.supporting_findings
        gaps = [finding for finding in findings if str(finding.get("kind", "")) in {"GAP", "CRITICAL_GAP"}]
        strengths = [finding for finding in findings if str(finding.get("kind", "")) == "STRENGTH"]
        critical_gaps = [finding for finding in gaps if str(finding.get("severity", "")).lower() in {"critical", "high"} or str(finding.get("category", "")).lower() in {"credential", "certification"}]
        experience_findings = [finding for finding in [*gaps, *strengths] if any(term in str(finding.get("category", "")).lower() for term in ["project", "career", "experience", "research", "internship"])]
        experience_strength = len(strengths) / max(1, len(experience_findings)) if experience_findings else 0.0

        unresolved = 0
        contradictory = 0
        approved = 0
        for evaluation in request.judge_evaluations:
            verdict = str(evaluation.get("verdict", ""))
            if verdict == JudgeVerdict.SUPPORTED.value:
                approved += 1
            else:
                unresolved += 1
            if verdict == JudgeVerdict.CONTRADICTED.value:
                contradictory += 1
        for claim in request.claims:
            verdict = str(claim.get("current_verdict", ""))
            if claim.get("external_verification_required") and verdict not in {JudgeVerdict.SUPPORTED.value, "NOT_APPLICABLE"}:
                unresolved += 1
            if verdict == JudgeVerdict.CONTRADICTED.value:
                contradictory += 1
            if verdict == JudgeVerdict.SUPPORTED.value:
                approved += 1

        stale_low = sum(
            1
            for evidence in request.evidence
            if _as_float(evidence.get("freshness_score")) < self.minimum_freshness
            or _as_float(evidence.get("source_quality_score")) < self.minimum_source_quality
            or str(evidence.get("verification_status", "")) == "REJECTED"
        )
        requirement_coverage = covered / len(requirements) if requirements else 0.0
        credential_coverage = credential_covered / credential_total if credential_total else 1.0
        feasibility = _preparation_feasibility(request.preparation_period, len(gaps))
        indicators = ReadinessIndicators(
            target_role_requirement_coverage=round(requirement_coverage, 3),
            critical_gap_count=len(critical_gaps),
            evidence_backed_experience_strength=round(min(experience_strength, 1.0), 3),
            preparation_period_feasibility=round(feasibility, 3),
            credential_requirement_coverage=round(credential_coverage, 3),
            unresolved_claim_count=unresolved,
            stale_or_low_quality_evidence_count=stale_low,
            contradictory_claim_count=contradictory,
            approved_claim_count=approved,
            total_requirement_count=len(requirements),
        )
        score = (
            0.25 * indicators.target_role_requirement_coverage
            + 0.15 * indicators.evidence_backed_experience_strength
            + 0.15 * indicators.preparation_period_feasibility
            + 0.15 * indicators.credential_requirement_coverage
            + 0.15 * (1.0 if unresolved == 0 else max(0.0, 1.0 - unresolved / max(1, len(request.claims))))
            + 0.15 * (1.0 if stale_low == 0 else max(0.0, 1.0 - stale_low / max(1, len(request.evidence))))
        )
        if unresolved or contradictory:
            score = min(score, 0.69 if not contradictory else 0.49)
        if indicators.critical_gap_count:
            score = min(score, 0.69)

        stable = (
            len(requirements) > 0
            and indicators.target_role_requirement_coverage >= 0.85
            and indicators.critical_gap_count == 0
            and indicators.evidence_backed_experience_strength >= 0.75
            and indicators.preparation_period_feasibility >= 0.75
            and indicators.credential_requirement_coverage >= 0.85
            and indicators.unresolved_claim_count == 0
            and indicators.contradictory_claim_count == 0
            and indicators.stale_or_low_quality_evidence_count == 0
        )
        appropriate = (
            indicators.target_role_requirement_coverage >= 0.5
            and indicators.critical_gap_count <= 2
            and indicators.contradictory_claim_count == 0
            and indicators.unresolved_claim_count <= 2
        )
        label = ReadinessLabel.STABLE if stable else ReadinessLabel.APPROPRIATE if appropriate else ReadinessLabel.RISK
        reasons = [
            f"requirement_coverage={indicators.target_role_requirement_coverage:.2f}",
            f"critical_gap_count={indicators.critical_gap_count}",
            f"experience_strength={indicators.evidence_backed_experience_strength:.2f}",
            f"preparation_feasibility={indicators.preparation_period_feasibility:.2f}",
            f"credential_coverage={indicators.credential_requirement_coverage:.2f}",
            f"unresolved_claim_count={indicators.unresolved_claim_count}",
            f"stale_or_low_quality_evidence_count={indicators.stale_or_low_quality_evidence_count}",
        ]
        limitations = []
        if not requirements:
            limitations.append("No market requirements were supplied; Stable is unavailable")
        if unresolved:
            limitations.append("Unresolved claims reduce confidence")
        if contradictory:
            limitations.append("Contradictory claims prevent Stable classification")
        if not request.judge_evaluations:
            limitations.append("No Judge evaluations were supplied")
        return ReadinessResponse(
            label=label,
            confidence=round(min(max(score, 0.0), 1.0), 3),
            indicators=indicators,
            reasons=reasons,
            limitations=limitations,
        )
