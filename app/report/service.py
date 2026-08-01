from __future__ import annotations

from typing import Any, Dict, Iterable, List

from app.metadata.models import WorkflowState

from .models import FinalReport


def _as_list(value: Any) -> List[Dict[str, Any]]:
    return [item for item in value if isinstance(item, dict)] if isinstance(value, list) else []


def _evidence_citations(ledger: Dict[str, Any]) -> List[Dict[str, Any]]:
    citations = []
    for evidence in _as_list(ledger.get("evidence", [])):
        url = evidence.get("source_url")
        if not url:
            continue
        citations.append({
            "evidence_id": evidence.get("evidence_id"),
            "claim_id": evidence.get("claim_id"),
            "title": evidence.get("source_title", ""),
            "publisher": evidence.get("publisher", ""),
            "url": url,
            "publication_date": evidence.get("publication_date"),
            "retrieval_date": evidence.get("retrieval_date"),
            "verification_status": evidence.get("verification_status"),
        })
    return citations


def _claim_refs(claims: Iterable[Dict[str, Any]]) -> List[Dict[str, Any]]:
    return [
        {
            "claim_id": claim.get("claim_id"),
            "claim_type": claim.get("claim_type"),
            "claim_text": claim.get("claim_text"),
            "evidence_ids": claim.get("evidence_ids", []),
            "verdict": claim.get("current_verdict"),
        }
        for claim in claims
        if claim.get("claim_id") and claim.get("claim_text")
    ]


def build_final_report(workflow: WorkflowState) -> FinalReport:
    metadata = workflow.user_confirmed_metadata or workflow.normalized_metadata
    ledger = workflow.evidence_ledger or {}
    readiness = workflow.readiness_classification
    planner = workflow.planner_result or {}
    market = workflow.market_analysis or {}
    supporting = workflow.supporting_findings
    recommendations = workflow.recommendations

    profile_items = [
        {
            "item_id": item.item_id,
            "category": item.category,
            "value": item.normalized_value,
            "provenance": item.provenance.value,
            "verification_status": item.verification_status.value,
            "source_page": item.source_page,
        }
        for item in metadata.items
    ]
    claims = _claim_refs(_as_list(ledger.get("claims", [])) or workflow.claims)
    warnings = list(dict.fromkeys([
        *workflow.warnings,
        *metadata.warnings,
        *(_as_list(ledger.get("warnings", []))),
    ]))
    uncertainty = list(dict.fromkeys([
        "This report is a conservative evidence-backed assessment, not an employment or acceptance guarantee.",
        "Sections without approved downstream results remain incomplete; missing evidence is not treated as a negative user fact.",
        *[str(item) for item in warnings if item],
    ]))

    status = "COMPLETE" if readiness or planner or market or supporting else "PARTIAL"
    summary = {
        "preferred_role": metadata.preferences.preferred_role,
        "preparation_period": metadata.preferences.preparation_period,
        "metadata_item_count": len(profile_items),
        "claim_count": len(claims),
        "evidence_count": len(_as_list(ledger.get("evidence", []))),
        "readiness_label": (readiness or {}).get("label") if isinstance(readiness, dict) else None,
    }
    return FinalReport(
        request_id=workflow.request_id,
        workflow_id=workflow.workflow_id,
        status=status,
        summary=summary,
        profile_summary={"preferences": metadata.preferences.model_dump(mode="json"), "items": profile_items},
        market_analysis=market,
        strengths=[item for item in supporting if item.get("finding_type") == "STRENGTH"],
        weaknesses=[item for item in supporting if item.get("finding_type") in {"WEAKNESS", "GAP"}],
        supporting_findings=supporting,
        readiness_classification=readiness,
        recommendations=recommendations,
        planner_result=planner,
        calendar_proposals=_as_list(planner.get("calendar_proposals", [])),
        todo_items=_as_list(planner.get("todo_items", [])),
        citations=_evidence_citations(ledger),
        uncertainty_notes=uncertainty,
        warnings=warnings,
        errors=list(workflow.errors),
        graph_status={
            "status": workflow.status,
            "next_nodes": workflow.next_nodes,
            "interrupt_required": workflow.interrupt_required,
            "checkpointed": workflow.checkpointed,
            "leading_agent": workflow.leading_agent,
            "claims": claims,
        },
    )
