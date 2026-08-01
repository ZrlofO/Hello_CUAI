import unittest
from datetime import date

from app.calendar.models import (
    AuthorizationStatus,
    CalendarBatchRequest,
    CalendarProposalApproval,
)
from app.calendar.service import CalendarService, MockAuthorizationBoundary, MockCalendarProvider
from app.planner.models import CalendarProposal, DateType


class CalendarFixtureTests(unittest.TestCase):
    def proposal(self, proposal_id="proposal-1", date_type=DateType.USER_CONFIRMED_DATE, eligible=True, deadline=None, evidence_ids=None):
        return CalendarProposal(
            proposal_id=proposal_id,
            task_id=f"task-{proposal_id}",
            title="Prepare portfolio review",
            target_start_date=date(2026, 8, 5),
            target_completion_date=date(2026, 8, 6),
            external_deadline=deadline,
            date_type=date_type,
            evidence_ids=evidence_ids or [],
            eligible_for_calendar=eligible,
        )

    def request(self, proposals, approvals=None, evidence=None, status=AuthorizationStatus.USER_APPROVED):
        return CalendarBatchRequest(
            authorization_status=status,
            proposals=proposals,
            approvals=approvals or [CalendarProposalApproval(proposal_id=proposals[0].proposal_id, approved=True)] if proposals else [],
            evidence=evidence or [],
            mock_mode=True,
        )

    def service(self, provider=None, status=AuthorizationStatus.USER_APPROVED):
        return CalendarService(provider or MockCalendarProvider(), MockAuthorizationBoundary(status))

    def test_user_approval_and_mock_event(self):
        result = self.service().create_approved_events(self.request([self.proposal()]))

        self.assertEqual(result.results[0].status, "MOCK_CREATED")
        self.assertFalse(result.external_write_performed)
        self.assertFalse(result.errors)

    def test_authorization_boundary_blocks_without_user_approval(self):
        result = self.service(status=AuthorizationStatus.USER_APPROVAL_REQUIRED).create_approved_events(self.request([self.proposal()], status=AuthorizationStatus.USER_APPROVAL_REQUIRED))

        self.assertEqual(result.results[0].error_code, "AUTHORIZATION_REQUIRED")
        self.assertFalse(result.external_write_performed)

    def test_unverified_external_deadline_is_blocked(self):
        proposal = self.proposal(
            date_type=DateType.VERIFIED_EXTERNAL_DATE,
            deadline=date(2026, 8, 20),
            evidence_ids=["evidence-1"],
        )
        result = self.service().create_approved_events(
            self.request(
                [proposal],
                evidence=[{
                    "evidence_id": "evidence-1",
                    "application_deadline": "2026-08-20",
                    "active_status_verified": True,
                    "verification_status": "UNVERIFIED",
                    "source_quality_score": 0.9,
                    "freshness_score": 0.9,
                }],
            )
        )

        self.assertEqual(result.results[0].error_code, "UNVERIFIED_DEADLINE")

    def test_user_confirmed_date_cannot_carry_unverified_external_deadline(self):
        proposal = self.proposal(deadline=date(2026, 8, 20), evidence_ids=[])
        result = self.service().create_approved_events(self.request([proposal]))

        self.assertEqual(result.results[0].error_code, "UNVERIFIED_DEADLINE")

    def test_duplicate_and_failed_events_are_independent(self):
        first = self.proposal("first")
        second = self.proposal("second")
        failing_provider = MockCalendarProvider(fail_proposal_ids={"second"})
        result = self.service(provider=failing_provider).create_approved_events(
            self.request(
                [first, second],
                approvals=[
                    CalendarProposalApproval(proposal_id="first", approved=True),
                    CalendarProposalApproval(proposal_id="second", approved=True),
                ],
            )
        )

        statuses = {item.proposal_id: item.status for item in result.results}
        self.assertEqual(statuses["first"], "MOCK_CREATED")
        self.assertEqual(statuses["second"], "FAILED")
        self.assertTrue(result.partial)

    def test_forbidden_date_types_are_blocked(self):
        proposal = self.proposal(date_type=DateType.TENTATIVE, eligible=True)
        result = self.service().create_approved_events(self.request([proposal]))

        self.assertEqual(result.results[0].error_code, "DATE_TYPE_NOT_ALLOWED")


if __name__ == "__main__":
    unittest.main()
