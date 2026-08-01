from __future__ import annotations

from typing import Any, Dict

from pydantic import ValidationError

from app.metadata.extraction import extract_pdf, normalize_extraction
from app.metadata.models import NormalizedMetadata, RawExtraction

from .state import WorkflowGraphState


def validate_request(state: WorkflowGraphState) -> Dict[str, Any]:
    filename = str(state.get("filename", ""))
    content_type = str(state.get("content_type", "application/pdf"))
    pdf_bytes = state.get("pdf_bytes", b"")
    errors = []
    if not state.get("request_id") or not state.get("workflow_id"):
        errors.append("request_id and workflow_id are required")
    if not filename or not filename.lower().endswith(".pdf"):
        errors.append("Only PDF files are supported")
    if content_type not in {"application/pdf", "application/octet-stream"}:
        errors.append("The uploaded file must have PDF MIME type")
    if not isinstance(pdf_bytes, bytes) or not pdf_bytes:
        errors.append("The uploaded PDF is empty")
    if errors:
        return {"status": "VALIDATION_ERROR", "errors": errors, "graph_error": "request_validation_failed"}
    return {"status": "REQUEST_VALIDATED", "errors": []}


def extract_pdf_text(state: WorkflowGraphState) -> Dict[str, Any]:
    if state.get("status") == "VALIDATION_ERROR":
        return {"status": "VALIDATION_ERROR"}
    try:
        raw = extract_pdf(
            state["pdf_bytes"],
            state["filename"],
            state.get("content_type", "application/pdf"),
        )
        return {
            "raw_extraction": raw.model_dump(mode="json"),
            "status": "PDF_EXTRACTED",
            "warnings": raw.warnings,
        }
    except (ValueError, RuntimeError) as exc:
        return {
            "status": "EXTRACTION_ERROR",
            "errors": [str(exc)],
            "graph_error": "pdf_extraction_failed",
        }


def normalize_metadata(state: WorkflowGraphState) -> Dict[str, Any]:
    if state.get("status") in {"VALIDATION_ERROR", "EXTRACTION_ERROR"}:
        return {"status": state.get("status")}
    try:
        raw = RawExtraction.model_validate(state["raw_extraction"])
        normalized = normalize_extraction(
            raw,
            preferred_role=state.get("preferred_role", ""),
            preparation_period=state.get("preparation_period", ""),
            additional_information=state.get("additional_information", ""),
        )
        return {
            "normalized_metadata": normalized.model_dump(mode="json"),
            "status": "METADATA_REVIEW_REQUIRED",
            "warnings": normalized.warnings,
        }
    except (ValidationError, KeyError, ValueError) as exc:
        return {
            "status": "SCHEMA_ERROR",
            "errors": [str(exc)],
            "graph_error": "metadata_schema_validation_failed",
        }


def metadata_review_interrupt(state: WorkflowGraphState) -> Dict[str, Any]:
    if state.get("status") in {"VALIDATION_ERROR", "EXTRACTION_ERROR", "SCHEMA_ERROR"}:
        return {"status": state.get("status")}
    return {"status": "METADATA_REVIEW_REQUIRED"}


def initialize_leading_agent(state: WorkflowGraphState) -> Dict[str, Any]:
    confirmed = state.get("user_confirmed_metadata")
    if not confirmed:
        return {
            "status": "INTERRUPT_REQUIRED",
            "errors": ["User-confirmed metadata is required before initialization"],
            "graph_error": "metadata_confirmation_required",
        }
    return {
        "status": "LEADING_AGENT_INITIALIZED",
        "leading_agent": {
            "name": "Leading Agent",
            "status": "READY",
            "input": "USER_CONFIRMED_METADATA",
        },
    }
