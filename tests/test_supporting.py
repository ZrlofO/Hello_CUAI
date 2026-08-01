import unittest

from app.metadata.models import MetadataItem, UserConfirmedMetadata
from app.supporting.models import (
    ConsultingReviewRequest,
    EvidenceState,
    FindingKind,
    SupportingAgentName,
    SupportingAgentOutput,
    SupportingAgentRequest,
    SupportingFinding,
)
from app.supporting.review import review_supporting_output
from app.supporting.runner import run_supporting_agents


class SupportingFixtureTests(unittest.TestCase):
    def metadata(self):
        return UserConfirmedMetadata(
            items=[
                MetadataItem(
                    category="projects",
                    normalized_value="AI engineer project",
                    provenance="USER_CORRECTED",
                    extraction_confidence=1.0,
                ),
                MetadataItem(
                    category="technical_skills",
                    normalized_value="Python, PyTorch",
                    provenance="USER_CORRECTED",
                    extraction_confidence=1.0,
                ),
            ],
            preferences={"preferred_role": "AI engineer", "preparation_period": "3 months"},
            revision=1,
        )

    def test_only_selected_scopes_are_activated_in_parallel_runner(self):
        request = SupportingAgentRequest(
            user_confirmed_metadata=self.metadata(),
            selected_categories=["projects"],
            market_requirements=[{"evidence_ids": ["evd_market"]}],
            claims=[{"claim_id": "clm_market"}],
            evidence_ids=["evd_market"],
        )

        result = run_supporting_agents(request)

        self.assertEqual(result.activated_agents, [SupportingAgentName.PROJECT_CAREER, SupportingAgentName.CV_POSITIONING])
        self.assertEqual(len(result.outputs), 2)
        self.assertTrue(all(output.findings for output in result.outputs))
        self.assertTrue(all("clm_market" in output.findings[0].claim_ids for output in result.outputs))

    def test_no_gap_selection_does_not_activate_every_agent(self):
        request = SupportingAgentRequest(user_confirmed_metadata=self.metadata())

        result = run_supporting_agents(request)

        self.assertEqual(result.activated_agents, [])
        self.assertEqual(result.outputs, [])
        self.assertTrue(result.warnings)

    def test_missing_evidence_is_not_confirmed_absence(self):
        request = SupportingAgentRequest(
            user_confirmed_metadata=self.metadata(),
            selected_categories=["leadership_and_contribution"],
        )
        result = run_supporting_agents(request)

        finding = result.outputs[0].findings[0]
        self.assertEqual(finding.evidence_state, EvidenceState.MISSING)
        self.assertNotEqual(finding.evidence_state, EvidenceState.CONFIRMED_ABSENCE)

    def test_review_rejects_unknown_references(self):
        finding = SupportingFinding(
            agent_name=SupportingAgentName.PROJECT_CAREER,
            category="project_career_experience",
            kind=FindingKind.STRENGTH,
            title="Traceability test",
            analysis="A structured finding",
            evidence_state=EvidenceState.PRESENT,
            metadata_item_ids=["item-1"],
            claim_ids=["clm_unknown"],
            evidence_ids=["evd_unknown"],
        )
        output = SupportingAgentOutput(agent_name=SupportingAgentName.PROJECT_CAREER, findings=[finding])

        review = review_supporting_output(
            ConsultingReviewRequest(
                supporting_output=output,
                available_claims=[],
                available_evidence_ids=[],
            )
        )

        self.assertEqual(review.outcome, "REVISION_REQUIRED")
        self.assertEqual(review.revision_finding_ids, [finding.finding_id])


if __name__ == "__main__":
    unittest.main()
