import unittest

from app.evidence.ledger import EvidenceLedger
from app.evidence.models import Claim, ClaimType, ClaimVerdict, Evidence


class EvidenceLedgerTests(unittest.TestCase):
    def test_external_claim_without_evidence_is_unverifiable(self):
        ledger = EvidenceLedger()
        claim = ledger.add_claim(
            Claim(
                claim_text="A current job requirement exists",
                claim_type=ClaimType.MARKET_FACT,
                produced_by="test",
                external_verification_required=True,
            )
        )

        result = ledger.validate()

        self.assertTrue(result.valid)
        self.assertIn(claim.claim_id, result.warnings[0])
        self.assertEqual(claim.current_verdict, ClaimVerdict.UNVERIFIABLE)

    def test_evidence_must_reference_an_existing_claim(self):
        ledger = EvidenceLedger()

        with self.assertRaises(ValueError):
            ledger.add_evidence(Evidence(claim_id="clm_missing", source_url="https://example.com"))

    def test_supported_claim_requires_evidence(self):
        ledger = EvidenceLedger()
        claim = ledger.add_claim(
            Claim(
                claim_text="A verified fact",
                claim_type=ClaimType.MARKET_FACT,
                produced_by="test",
                current_verdict=ClaimVerdict.SUPPORTED,
            )
        )

        result = ledger.validate()

        self.assertFalse(result.valid)
        self.assertTrue(any(claim.claim_id in error for error in result.errors))

    def test_claim_and_evidence_can_be_linked(self):
        ledger = EvidenceLedger()
        claim = ledger.add_claim(
            Claim(
                claim_text="An official requirement was published",
                claim_type=ClaimType.JOB_POSTING_FACT,
                produced_by="retrieval",
                external_verification_required=True,
            )
        )
        evidence = ledger.add_evidence(
            Evidence(
                claim_id=claim.claim_id,
                source_url="https://example.com/job",
                source_title="Official job posting",
                source_quality_score=0.9,
                relevance_score=0.9,
            )
        )
        ledger.attach_evidence(claim.claim_id, evidence.evidence_id)

        result = ledger.validate()

        self.assertTrue(result.valid)
        self.assertEqual(claim.evidence_ids, [evidence.evidence_id])

    def test_source_quality_and_freshness_use_deterministic_scores(self):
        ledger = EvidenceLedger()
        claim = ledger.add_claim(
            Claim(
                claim_text="An official requirement was published",
                claim_type=ClaimType.JOB_POSTING_FACT,
                produced_by="retrieval",
                external_verification_required=True,
            )
        )
        evidence = ledger.add_evidence(
            Evidence(
                claim_id=claim.claim_id,
                source_type="OFFICIAL_COMPANY",
                source_url="https://example.com/job",
                publication_date="2026-07-01",
            )
        )

        self.assertEqual(evidence.source_quality_score, 0.95)
        self.assertGreater(evidence.freshness_score, 0.0)


if __name__ == "__main__":
    unittest.main()
