import unittest

from app.metadata.models import MetadataItem, UserConfirmedMetadata
from app.readiness.models import ReadinessLabel, ReadinessRequest
from app.readiness.policy import ReadinessPolicy


class ReadinessFixtureTests(unittest.TestCase):
    def metadata(self):
        return UserConfirmedMetadata(
            items=[
                MetadataItem(category="technical_skills", normalized_value="Python PyTorch", provenance="USER_CORRECTED", extraction_confidence=1.0),
                MetadataItem(category="projects", normalized_value="AI engineer project", provenance="USER_CORRECTED", extraction_confidence=1.0),
                MetadataItem(category="certifications_and_credentials", normalized_value="AWS certification", provenance="USER_CORRECTED", extraction_confidence=1.0),
            ],
            preferences={"preferred_role": "AI engineer", "preparation_period": "3 months"},
            revision=1,
        )

    def base_request(self, **overrides):
        payload = {
            "user_confirmed_metadata": self.metadata(),
            "preferred_role": "AI engineer",
            "preparation_period": "3 months",
            "market_requirements": [
                {"requirement": "Python PyTorch", "normalized_requirement": "Python PyTorch", "requirement_type": "skill"},
                {"requirement": "AWS certification", "normalized_requirement": "AWS certification", "requirement_type": "credential"},
            ],
            "claims": [
                {"claim_id": "claim-market", "external_verification_required": True, "current_verdict": "SUPPORTED"}
            ],
            "evidence": [
                {"evidence_id": "evidence-market", "source_quality_score": 0.9, "freshness_score": 0.9, "verification_status": "VERIFIED"}
            ],
            "supporting_findings": [
                {"kind": "STRENGTH", "category": "project_career_experience"}
            ],
            "judge_evaluations": [{"claim_id": "claim-market", "verdict": "SUPPORTED"}],
        }
        payload.update(overrides)
        return ReadinessRequest(**payload)

    def test_stable_requires_all_strict_gates(self):
        result = ReadinessPolicy().classify(self.base_request())

        self.assertEqual(result.label, ReadinessLabel.STABLE)
        self.assertGreaterEqual(result.confidence, 0.75)
        self.assertIn("employment or acceptance guarantee", result.disclaimer)

    def test_unresolved_claim_blocks_stable(self):
        result = ReadinessPolicy().classify(
            self.base_request(
                judge_evaluations=[{"claim_id": "claim-market", "verdict": "AMBIGUOUS"}]
            )
        )

        self.assertNotEqual(result.label, ReadinessLabel.STABLE)
        self.assertTrue(result.indicators.unresolved_claim_count > 0)
        self.assertTrue(result.limitations)

    def test_contradiction_forces_risk(self):
        result = ReadinessPolicy().classify(
            self.base_request(
                judge_evaluations=[{"claim_id": "claim-market", "verdict": "CONTRADICTED"}]
            )
        )

        self.assertEqual(result.label, ReadinessLabel.RISK)
        self.assertEqual(result.indicators.contradictory_claim_count, 1)

    def test_no_market_requirements_cannot_be_stable(self):
        result = ReadinessPolicy().classify(self.base_request(market_requirements=[]))

        self.assertNotEqual(result.label, ReadinessLabel.STABLE)
        self.assertIn("No market requirements", " ".join(result.limitations))


if __name__ == "__main__":
    unittest.main()
