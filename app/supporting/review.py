from __future__ import annotations

from typing import Dict, Set

from .models import ConsultingReviewRequest, ConsultingReviewResponse, EvidenceState


def review_supporting_output(request: ConsultingReviewRequest) -> ConsultingReviewResponse:
    output = request.supporting_output
    claim_ids: Set[str] = {claim.get("claim_id") for claim in request.available_claims if claim.get("claim_id")}
    evidence_ids = set(request.available_evidence_ids)
    approved = []
    revision = []
    more_evidence = []
    unverifiable = []
    reasons = list(output.errors)

    for finding in output.findings:
        invalid_claims = set(finding.claim_ids) - claim_ids
        invalid_evidence = set(finding.evidence_ids) - evidence_ids
        if invalid_claims or invalid_evidence or finding.unsupported_claim:
            revision.append(finding.finding_id)
            reasons.append(f"Finding {finding.finding_id} has unsupported or unknown references")
            continue
        if finding.evidence_state in {EvidenceState.MISSING, EvidenceState.UNCERTAIN} and not finding.evidence_ids:
            more_evidence.append(finding.finding_id)
            reasons.append(f"Finding {finding.finding_id} needs additional evidence")
            continue
        if finding.evidence_state == EvidenceState.CONFIRMED_ABSENCE and not finding.metadata_item_ids:
            approved.append(finding.finding_id)
            continue
        if not finding.metadata_item_ids and not finding.claim_ids:
            unverifiable.append(finding.finding_id)
            reasons.append(f"Finding {finding.finding_id} has no traceability references")
            continue
        approved.append(finding.finding_id)

    if output.status == "FAILED":
        outcome = "REVISION_REQUIRED"
    elif revision:
        outcome = "REVISION_REQUIRED"
    elif more_evidence:
        outcome = "MORE_EVIDENCE_REQUIRED"
    elif unverifiable:
        outcome = "UNVERIFIABLE"
    else:
        outcome = "APPROVED"
    return ConsultingReviewResponse(
        agent_name=output.agent_name,
        outcome=outcome,
        approved_finding_ids=approved,
        revision_finding_ids=revision,
        more_evidence_finding_ids=more_evidence,
        unverifiable_finding_ids=unverifiable,
        reasons=reasons,
    )
