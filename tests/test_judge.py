import unittest

from app.judge.models import (
    AdaptiveDebateConfig,
    JudgeClaimInput,
    JudgeEvaluation,
    JudgeEvidenceInput,
    JudgeRequest,
    JudgeVerdict,
    RoutingDecision,
)
from app.judge.service import DeterministicJudge, JudgeProvider, JudgeService


class AlwaysAmbiguousJudge(JudgeProvider):
    mode = "fixture_ambiguous"

    def evaluate(self, claim, evidence, config, round_number, retry_count):
        return JudgeEvaluation(
            claim_id=claim.claim_id,
            verdict=JudgeVerdict.AMBIGUOUS,
            evidence_used_ids=claim.evidence_ids,
            contradicting_evidence_ids=[],
            evidence_status="AMBIGUOUS",
            source_quality=0.8,
            freshness=0.8,
            confidence=0.4,
            reason="Fixture keeps the claim unresolved",
            required_next_action=RoutingDecision.ESCALATE_TO_JUDGE,
            judge_mode=self.mode,
            debate_round=round_number,
            retry_count=retry_count,
        )


class JudgeFixtureTests(unittest.TestCase):
    def claim(self, evidence_ids=None, external=True):
        return JudgeClaimInput(
            claim_id="clm_fixture",
            claim_text="The official posting requires Python",
            claim_type="job_posting_fact",
            evidence_ids=evidence_ids or [],
            external_verification_required=external,
        )

    def evidence(self, evidence_id="evd_fixture", support_status="SUPPORTS"):
        return JudgeEvidenceInput(
            evidence_id=evidence_id,
            source_url="https://example.com/job",
            relevant_excerpt="Python is required",
            source_quality_score=0.9,
            freshness_score=0.9,
            relevance_score=0.9,
            support_status=support_status,
            verification_status="VERIFIED",
        )

    def test_external_claim_without_evidence_is_unverifiable(self):
        result = JudgeService(provider=DeterministicJudge()).debate(
            JudgeRequest(claims=[self.claim()], evidence=[])
        )

        self.assertEqual(result.evaluations[0].verdict, JudgeVerdict.UNVERIFIABLE)
        self.assertEqual(result.routing["clm_fixture"], RoutingDecision.UNVERIFIABLE)

    def test_supported_and_contradicted_verdicts_are_atomic(self):
        supported = JudgeService(provider=DeterministicJudge()).debate(
            JudgeRequest(claims=[self.claim(["evd_support"])], evidence=[self.evidence("evd_support")])
        )
        contradicted = JudgeService(provider=DeterministicJudge()).debate(
            JudgeRequest(claims=[self.claim(["evd_contra"])], evidence=[self.evidence("evd_contra", "CONTRADICTS")])
        )

        self.assertEqual(supported.evaluations[0].verdict, JudgeVerdict.SUPPORTED)
        self.assertEqual(contradicted.evaluations[0].verdict, JudgeVerdict.CONTRADICTED)
        self.assertEqual(contradicted.evaluations[0].contradicting_evidence_ids, ["evd_contra"])

    def test_debate_is_bounded_and_ends_unverifiable(self):
        service = JudgeService(provider=AlwaysAmbiguousJudge())
        result = service.debate(
            JudgeRequest(
                claims=[self.claim(["evd_fixture"])],
                evidence=[self.evidence()],
                max_debate_rounds=2,
                max_retries=1,
            )
        )

        self.assertEqual(result.evaluations[0].verdict, JudgeVerdict.UNVERIFIABLE)
        self.assertEqual(result.retry_counts["clm_fixture"], 1)
        self.assertTrue(result.partial)

    def test_provider_failure_falls_back_to_deterministic_mock(self):
        class BrokenJudge(JudgeProvider):
            def evaluate(self, *args, **kwargs):
                raise RuntimeError("fixture provider failure")

        result = JudgeService(provider=BrokenJudge()).debate(
            JudgeRequest(claims=[self.claim(["evd_fixture"])], evidence=[self.evidence()])
        )

        self.assertEqual(result.evaluations[0].judge_mode, "deterministic_mock")
        self.assertEqual(result.evaluations[0].verdict, JudgeVerdict.SUPPORTED)


if __name__ == "__main__":
    unittest.main()
