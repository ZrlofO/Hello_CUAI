import unittest

from app.planner.models import DateType, PlannerRequest
from app.planner.service import PlannerAgent


class PlannerFixtureTests(unittest.TestCase):
    def evidence(self, deadline="2026-08-20", status="VERIFIED", active=True):
        return {
            "evidence_id": "evd-event",
            "application_deadline": deadline,
            "active_status_verified": active,
            "verification_status": status,
            "source_quality_score": 0.9,
            "freshness_score": 0.9,
        }

    def candidate(self, **updates):
        candidate = {
            "candidate_id": "candidate-1",
            "finding_id": "finding-1",
            "approved": True,
            "category": "credential",
            "title": "Apply to the verified certification program",
            "reason": "The approved finding identifies a credential gap.",
            "related_gap": "credential coverage",
            "evidence_ids": ["evd-event"],
            "priority": "HIGH",
            "estimated_effort": "2 weeks",
            "external_deadline": "2026-08-20",
        }
        candidate.update(updates)
        return candidate

    def test_verified_deadline_becomes_external_date_and_calendar_proposal(self):
        result = PlannerAgent().plan(
            PlannerRequest(
                recommendation_candidates=[self.candidate()],
                evidence=[self.evidence()],
            )
        )

        item = result.todo_items[0]
        proposal = result.calendar_proposals[0]
        self.assertEqual(item.date_type, DateType.VERIFIED_EXTERNAL_DATE)
        self.assertEqual(item.external_deadline.isoformat(), "2026-08-20")
        self.assertTrue(proposal.eligible_for_calendar)
        self.assertFalse(result.calendar_write_enabled)

    def test_unverified_deadline_is_not_saved_as_external_deadline(self):
        result = PlannerAgent().plan(
            PlannerRequest(
                recommendation_candidates=[self.candidate(tentative=True)],
                evidence=[self.evidence(status="UNVERIFIED")],
            )
        )

        item = result.todo_items[0]
        self.assertIsNone(item.external_deadline)
        self.assertEqual(item.date_type, DateType.TENTATIVE)
        self.assertFalse(result.calendar_proposals[0].eligible_for_calendar)

    def test_expired_opportunity_is_excluded_from_calendar(self):
        result = PlannerAgent().plan(
            PlannerRequest(
                recommendation_candidates=[self.candidate(external_deadline="2026-07-01")],
                evidence=[self.evidence(deadline="2026-07-01")],
            )
        )

        self.assertFalse(result.calendar_proposals[0].eligible_for_calendar)
        self.assertEqual(result.calendar_proposals[0].exclusion_reason, "Expired external opportunity")

    def test_only_approved_candidates_are_used_and_guarantee_is_rejected(self):
        result = PlannerAgent().plan(
            PlannerRequest(
                recommendation_candidates=[
                    self.candidate(),
                    self.candidate(candidate_id="candidate-2", approved=False, title="Guaranteed acceptance"),
                ],
                evidence=[self.evidence()],
            )
        )

        self.assertEqual(len(result.todo_items), 1)
        self.assertFalse(result.errors)

    def test_no_approved_candidate_returns_warning(self):
        result = PlannerAgent().plan(PlannerRequest(recommendation_candidates=[]))

        self.assertEqual(result.todo_items, [])
        self.assertTrue(result.warnings)


if __name__ == "__main__":
    unittest.main()
