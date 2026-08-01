from __future__ import annotations

from typing import Any, Dict, List, Optional, TypedDict


class WorkflowGraphState(TypedDict, total=False):
    request_id: str
    workflow_id: str
    status: str
    filename: str
    content_type: str
    pdf_bytes: bytes
    preferred_role: str
    preparation_period: str
    additional_information: str
    raw_extraction: Dict[str, Any]
    normalized_metadata: Dict[str, Any]
    user_confirmed_metadata: Optional[Dict[str, Any]]
    metadata_revision: int
    leading_agent: Dict[str, Any]
    claims: List[Dict[str, Any]]
    evidence_ledger: Dict[str, Any]
    errors: List[str]
    warnings: List[str]
    graph_error: Optional[str]
