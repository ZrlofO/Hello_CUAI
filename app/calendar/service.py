from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import date
from typing import Dict, Iterable, List, Optional, Protocol, Set, Tuple

from app.evidence.models import EvidenceStatus
from app.planner.models import CalendarProposal, DateType

from .models import (
    AuthorizationStatus,
    CalendarBatchRequest,
    CalendarBatchResponse,
    CalendarWriteResult,
)


class CalendarAuthorizationBoundary(Protocol):
    """Future OAuth boundary. This interface never stores or logs credentials."""

    def status(self) -> AuthorizationStatus: ...


class MockAuthorizationBoundary:
    def __init__(self, authorization_status: AuthorizationStatus):
        self._status = authorization_status

    def status(self) -> AuthorizationStatus:
        return self._status


class CalendarProvider(Protocol):
    name: str

    def create_event(self, proposal: CalendarProposal, start: Optional[date], end: Optional[date]) -> CalendarWriteResult: ...


class MockCalendarProvider:
    name = "mock"

    def __init__(self, fail_proposal_ids: Optional[Set[str]] = None, timeout_proposal_ids: Optional[Set[str]] = None):
        self.fail_proposal_ids = fail_proposal_ids or set()
        self.timeout_proposal_ids = timeout_proposal_ids or set()
        self.events: Dict[str, CalendarWriteResult] = {}

    def create_event(self, proposal: CalendarProposal, start: Optional[date], end: Optional[date]) -> CalendarWriteResult:
        if proposal.proposal_id in self.timeout_proposal_ids:
            return CalendarWriteResult(proposal_id=proposal.proposal_id, status="FAILED", error_code="PROVIDER_TIMEOUT", message="Mock provider timeout")
        if proposal.proposal_id in self.fail_proposal_ids:
            return CalendarWriteResult(proposal_id=proposal.proposal_id, status="FAILED", error_code="PROVIDER_ERROR", message="Mock provider failure")
        if not start and not end:
            return CalendarWriteResult(proposal_id=proposal.proposal_id, status="FAILED", error_code="INVALID_DATE", message="Calendar event requires a start or end date")
        fingerprint = f"{proposal.title.lower()}|{start}|{end}"
        if fingerprint in self.events:
            return CalendarWriteResult(proposal_id=proposal.proposal_id, status="SKIPPED", error_code="DUPLICATE_EVENT", message="Mock duplicate event detected")
        result = CalendarWriteResult(
            proposal_id=proposal.proposal_id,
            status="MOCK_CREATED",
            event_id=f"mock_event_{len(self.events) + 1}",
            message="Mock calendar event created in memory; no external write was performed",
        )
        self.events[fingerprint] = result
        return result


class CalendarService:
    def __init__(self, provider: CalendarProvider, authorization: CalendarAuthorizationBoundary):
        self.provider = provider
        self.authorization = authorization

    def create_approved_events(self, request: CalendarBatchRequest) -> CalendarBatchResponse:
        response = CalendarBatchResponse(provider=getattr(self.provider, "name", "unknown"))
        auth_status = self.authorization.status()
        if auth_status != AuthorizationStatus.USER_APPROVED:
            response.warnings.append(f"Calendar authorization boundary is not approved: {auth_status.value}")
            for proposal in request.proposals:
                response.results.append(CalendarWriteResult(proposal_id=proposal.proposal_id, status="BLOCKED", error_code="AUTHORIZATION_REQUIRED", message="User calendar approval is required"))
            response.partial = bool(request.proposals)
            return response
        if not request.mock_mode or getattr(self.provider, "name", "") != "mock":
            response.errors.append("External calendar providers are disabled in this phase")
            response.partial = bool(request.proposals)
            return response

        approvals = {approval.proposal_id: approval for approval in request.approvals if approval.approved}
        evidence_by_id = {str(item.get("evidence_id")): item for item in request.evidence if item.get("evidence_id")}
        seen_proposals: Set[str] = set()
        for proposal in request.proposals:
            try:
                result = self._process_proposal(proposal, approvals.get(proposal.proposal_id), evidence_by_id, seen_proposals)
                response.results.append(result)
                if result.status in {"FAILED", "BLOCKED"}:
                    response.partial = True
            except Exception as exc:
                response.results.append(CalendarWriteResult(proposal_id=proposal.proposal_id, status="FAILED", error_code="INTERNAL_ERROR", message=f"Calendar proposal failed safely: {exc.__class__.__name__}"))
                response.partial = True
        return response

    def _process_proposal(self, proposal, approval, evidence_by_id, seen_proposals):
        if proposal.proposal_id in seen_proposals:
            return CalendarWriteResult(proposal_id=proposal.proposal_id, status="SKIPPED", error_code="DUPLICATE_PROPOSAL", message="Duplicate proposal in request")
        seen_proposals.add(proposal.proposal_id)
        if not approval:
            return CalendarWriteResult(proposal_id=proposal.proposal_id, status="BLOCKED", error_code="USER_APPROVAL_REQUIRED", message="Proposal was not approved by the user")
        if not proposal.eligible_for_calendar:
            return CalendarWriteResult(proposal_id=proposal.proposal_id, status="BLOCKED", error_code="PROPOSAL_NOT_ELIGIBLE", message=proposal.exclusion_reason or "Proposal is not calendar eligible")
        if proposal.date_type not in {DateType.VERIFIED_EXTERNAL_DATE, DateType.USER_CONFIRMED_DATE}:
            return CalendarWriteResult(proposal_id=proposal.proposal_id, status="BLOCKED", error_code="DATE_TYPE_NOT_ALLOWED", message="Only verified external or user-confirmed dates are allowed")
        if proposal.external_deadline and not self._verified_deadline(proposal, evidence_by_id):
            return CalendarWriteResult(proposal_id=proposal.proposal_id, status="BLOCKED", error_code="UNVERIFIED_DEADLINE", message="External deadline lacks verified evidence")
        start = approval.user_confirmed_start or proposal.target_start_date
        end = approval.user_confirmed_end or proposal.target_completion_date
        if start and end and start > end:
            return CalendarWriteResult(proposal_id=proposal.proposal_id, status="FAILED", error_code="INVALID_DATE", message="Start date must not be after end date")
        if proposal.external_deadline and proposal.external_deadline < date.today():
            return CalendarWriteResult(proposal_id=proposal.proposal_id, status="BLOCKED", error_code="EXPIRED_OPPORTUNITY", message="Expired opportunities cannot become calendar events")
        return self.provider.create_event(proposal, start, end)

    @staticmethod
    def _verified_deadline(proposal, evidence_by_id) -> bool:
        if not proposal.external_deadline:
            return False
        for evidence_id in proposal.evidence_ids:
            evidence = evidence_by_id.get(evidence_id)
            if not evidence:
                continue
            if (
                evidence.get("application_deadline") == proposal.external_deadline.isoformat()
                and evidence.get("active_status_verified") is not False
                and evidence.get("verification_status") in {EvidenceStatus.VERIFIED.value, EvidenceStatus.SUPPORTS.value}
                and float(evidence.get("source_quality_score", 0.0)) >= 0.4
                and float(evidence.get("freshness_score", 0.0)) >= 0.25
            ):
                return True
        return False
