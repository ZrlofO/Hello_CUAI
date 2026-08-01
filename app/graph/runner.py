from __future__ import annotations

import os
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeoutError
from typing import Any, Dict

from .builder import workflow_graph


GRAPH_TIMEOUT_SECONDS = float(os.getenv("LANGGRAPH_GRAPH_TIMEOUT_SECONDS", "60"))


class GraphExecutionTimeout(RuntimeError):
    pass


def graph_config(workflow_id: str) -> Dict[str, Any]:
    return {"configurable": {"thread_id": workflow_id, "workflow_id": workflow_id}}


def _invoke(input_state, config):
    return workflow_graph.invoke(input_state, config=config)


def invoke_graph(input_state, workflow_id: str):
    config = graph_config(workflow_id)
    with ThreadPoolExecutor(max_workers=1) as executor:
        future = executor.submit(_invoke, input_state, config)
        try:
            future.result(timeout=GRAPH_TIMEOUT_SECONDS)
        except FutureTimeoutError as exc:
            raise GraphExecutionTimeout(f"Graph execution exceeded {GRAPH_TIMEOUT_SECONDS:g} seconds") from exc
    return graph_snapshot(workflow_id)


def resume_graph(workflow_id: str, confirmed_metadata: Dict[str, Any], revision: int):
    config = graph_config(workflow_id)
    workflow_graph.update_state(
        config,
        {
            "user_confirmed_metadata": confirmed_metadata,
            "metadata_revision": revision,
            "status": "METADATA_CONFIRMED",
        },
        as_node="metadata_review_interrupt",
    )
    return invoke_graph(None, workflow_id)


def graph_snapshot(workflow_id: str) -> Dict[str, Any]:
    snapshot = workflow_graph.get_state(graph_config(workflow_id))
    values = dict(snapshot.values or {})
    values.pop("pdf_bytes", None)
    values["workflow_id"] = workflow_id
    values["next_nodes"] = list(snapshot.next or ())
    values["interrupt_required"] = bool(snapshot.next and "initialize_leading_agent" in snapshot.next)
    values["checkpointed"] = True
    return values
