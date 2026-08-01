from __future__ import annotations

import re
from datetime import date, timedelta
from typing import Any, Dict, List, Optional, Set, Tuple
from uuid import uuid4

from app.evidence.models import EvidenceStatus

from .models import CalendarProposal, DateType, PlannerRequest, PlannerResponse, TodoItem, TodoStatus


FORBIDDEN_GUARANTEE_TERMS = ("guaranteed", "guarantee", "will be accepted", "합격 보장", "취업 보장", "100% 합격")


def _parse_date(value: Any) -> Optional[date]:
    if not value:
        return None
    if isinstance(value, date):
        return value
    match = re.search(r"(20\d{2})[-/.](\d{1,2})[-/.](\d{1,2})", str(value))
    if not match:
        return None
    try:
        return date(int(match.group(1)), int(match.group(2)), int(match.group(3)))
    except ValueError:
        return None


def _contains_guarantee(value: str) -> bool:
    lowered = value.lower()
    return any(term in lowered for term in FORBIDDEN_GUARANTEE_TERMS)


class PlannerAgent:
    def plan(self, request: PlannerRequest) -> PlannerResponse:
        response = PlannerResponse(calendar_write_enabled=False)
        evidence_by_id = {str(item.get("evidence_id")): item for item in request.evidence if item.get("evidence_id")}
        approved_findings = {
            finding_id for finding_id in request.approved_finding_ids if finding_id
        }
        finding_map = {str(item.get("finding_id")): item for item in request.supporting_findings if item.get("finding_id")}
        candidates = [candidate for candidate in request.recommendation_candidates if self._candidate_approved(candidate, approved_findings, finding_map)]
        if not candidates:
            response.warnings.append("No approved finding or recommendation candidate was supplied")
            return response

        for candidate in candidates:
            try:
                item, proposal = self._build_item(candidate, evidence_by_id, request)
                if item:
                    response.todo_items.append(item)
                if proposal:
                    response.calendar_proposals.append(proposal)
            except Exception as exc:
                response.errors.append(f"Planner item failed safely: {exc.__class__.__name__}")
                response.partial = True
        if response.errors or response.warnings:
            response.partial = True
        return response

    @staticmethod
    def _candidate_approved(candidate: Dict[str, Any], approved_ids: Set[str], findings: Dict[str, Dict[str, Any]]) -> bool:
        if candidate.get("status") in {"REJECTED", "UNVERIFIED", "PENDING"}:
            return False
        finding_id = str(candidate.get("finding_id", candidate.get("related_finding_id", "")))
        if candidate.get("approved") is True or candidate.get("review_outcome") == "APPROVED":
            return True
        return bool(finding_id and finding_id in approved_ids and findings.get(finding_id))

    def _build_item(self, candidate: Dict[str, Any], evidence_by_id: Dict[str, Dict[str, Any]], request: PlannerRequest) -> Tuple[Optional[TodoItem], Optional[CalendarProposal]]:
        title = str(candidate.get("title", "")).strip()
        reason = str(candidate.get("reason", "")).strip()
        if not title or not reason:
            raise ValueError("approved planner candidate requires title and reason")
        if _contains_guarantee(title) or _contains_guarantee(reason):
            raise ValueError("employment guarantee wording is not allowed")
        evidence_ids = [str(item) for item in candidate.get("evidence_ids", []) if str(item) in evidence_by_id]
        valid_evidence = [evidence_by_id[item] for item in evidence_ids]
        verified_deadline = self._verified_deadline(candidate, valid_evidence)
        raw_external_deadline = _parse_date(candidate.get("external_deadline"))
        if raw_external_deadline and verified_deadline is None:
            # Never preserve an unverified external deadline.
            raw_external_deadline = None
        external_deadline = verified_deadline or raw_external_deadline
        user_start = _parse_date(request.user_confirmed_dates.get(str(candidate.get("candidate_id", "")), {}).get("start")) if isinstance(request.user_confirmed_dates.get(str(candidate.get("candidate_id", ""))), dict) else None
        user_end = _parse_date(request.user_confirmed_dates.get(str(candidate.get("candidate_id", "")), {}).get("end")) if isinstance(request.user_confirmed_dates.get(str(candidate.get("candidate_id", ""))), dict) else None
        suggested_start = _parse_date(candidate.get("target_start_date"))
        suggested_end = _parse_date(candidate.get("target_completion_date"))
        start = user_start or suggested_start
        end = user_end or suggested_end
        if user_start or user_end:
            date_type = DateType.USER_CONFIRMED_DATE
        elif verified_deadline:
            date_type = DateType.VERIFIED_EXTERNAL_DATE
            end = end or verified_deadline
        elif start or end:
            date_type = DateType.PLANNER_SUGGESTED_DATE
        elif candidate.get("tentative"):
            date_type = DateType.TENTATIVE
        else:
            date_type = DateType.UNSCHEDULED
        status = TodoStatus.USER_CONFIRMATION_REQUIRED if date_type in {DateType.TENTATIVE, DateType.PLANNER_SUGGESTED_DATE} else TodoStatus.PROPOSED
        item = TodoItem(
            task_id=str(candidate.get("task_id") or candidate.get("candidate_id") or f"task_{uuid4().hex}"),
            category=str(candidate.get("category", "general")),
            title=title,
            reason=reason,
            related_gap=str(candidate.get("related_gap", "")),
            evidence_ids=evidence_ids,
            priority=str(candidate.get("priority", "MEDIUM")).upper(),
            estimated_effort=str(candidate.get("estimated_effort", "")),
            target_start_date=start,
            target_completion_date=end,
            external_deadline=external_deadline,
            date_type=date_type,
            status=status,
            dependencies=[str(value) for value in candidate.get("dependencies", [])],
        )
        proposal = self._proposal(item, valid_evidence, verified_deadline)
        return item, proposal

    @staticmethod
    def _verified_deadline(candidate: Dict[str, Any], evidence: List[Dict[str, Any]]) -> Optional[date]:
        deadline = _parse_date(candidate.get("external_deadline"))
        if not deadline:
            return None
        for item in evidence:
            evidence_deadline = _parse_date(item.get("application_deadline"))
            if (
                evidence_deadline == deadline
                and item.get("active_status_verified") is not False
                and item.get("verification_status") in {EvidenceStatus.VERIFIED.value, EvidenceStatus.SUPPORTS.value}
                and float(item.get("source_quality_score", 0.0)) >= 0.4
                and float(item.get("freshness_score", 0.0)) >= 0.25
            ):
                return deadline
        return None

    @staticmethod
    def _proposal(item: TodoItem, evidence: List[Dict[str, Any]], verified_deadline: Optional[date]) -> CalendarProposal:
        if item.external_deadline and verified_deadline and item.external_deadline < date.today():
            return CalendarProposal(
                task_id=item.task_id,
                title=item.title,
                target_start_date=item.target_start_date,
                target_completion_date=item.target_completion_date,
                external_deadline=item.external_deadline,
                date_type=item.date_type,
                evidence_ids=item.evidence_ids,
                eligible_for_calendar=False,
                exclusion_reason="Expired external opportunity",
            )
        eligible = item.date_type in {DateType.VERIFIED_EXTERNAL_DATE, DateType.USER_CONFIRMED_DATE} and bool(item.target_start_date or item.target_completion_date)
        return CalendarProposal(
            task_id=item.task_id,
            title=item.title,
            target_start_date=item.target_start_date,
            target_completion_date=item.target_completion_date,
            external_deadline=item.external_deadline,
            date_type=item.date_type,
            evidence_ids=item.evidence_ids,
            eligible_for_calendar=eligible,
            exclusion_reason=None if eligible else "Calendar write requires a verified or user-confirmed date",
        )
