from __future__ import annotations

from langgraph.graph import END, START, StateGraph

from .checkpoints import checkpoint_manager
from .nodes import (
    extract_pdf_text,
    initialize_leading_agent,
    metadata_review_interrupt,
    normalize_metadata,
    validate_request,
)
from .state import WorkflowGraphState


def _route_after_validation(state: WorkflowGraphState):
    return "error" if state.get("status") == "VALIDATION_ERROR" else "extract_pdf_text"


def _route_after_extraction(state: WorkflowGraphState):
    return "error" if state.get("status") == "EXTRACTION_ERROR" else "normalize_metadata"


def _route_after_normalization(state: WorkflowGraphState):
    return "error" if state.get("status") == "SCHEMA_ERROR" else "metadata_review_interrupt"


def _error_node(state: WorkflowGraphState):
    return {"status": state.get("status", "GRAPH_ERROR")}


def build_workflow_graph():
    graph = StateGraph(WorkflowGraphState)
    graph.add_node("validate_request", validate_request)
    graph.add_node("extract_pdf_text", extract_pdf_text)
    graph.add_node("normalize_metadata", normalize_metadata)
    graph.add_node("metadata_review_interrupt", metadata_review_interrupt)
    graph.add_node("initialize_leading_agent", initialize_leading_agent)
    graph.add_node("error", _error_node)
    graph.add_edge(START, "validate_request")
    graph.add_conditional_edges("validate_request", _route_after_validation, {"extract_pdf_text": "extract_pdf_text", "error": "error"})
    graph.add_conditional_edges("extract_pdf_text", _route_after_extraction, {"normalize_metadata": "normalize_metadata", "error": "error"})
    graph.add_conditional_edges("normalize_metadata", _route_after_normalization, {"metadata_review_interrupt": "metadata_review_interrupt", "error": "error"})
    graph.add_edge("metadata_review_interrupt", "initialize_leading_agent")
    graph.add_edge("initialize_leading_agent", END)
    graph.add_edge("error", END)
    return graph.compile(checkpointer=checkpoint_manager.saver, interrupt_before=["initialize_leading_agent"])


workflow_graph = build_workflow_graph()
