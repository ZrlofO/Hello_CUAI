from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Dict, List

from .agents import AGENT_CLASSES
from .models import SupportingAgentName, SupportingAgentRequest, SupportingAgentOutput, SupportingRunResponse


def selected_agent_names(selected_categories: List[str]) -> List[SupportingAgentName]:
    selected = set(selected_categories)
    if not selected:
        return []
    return [
        name for name, agent in AGENT_CLASSES.items()
        if selected.intersection(agent.categories) or name.value in selected
    ]


def run_supporting_agents(request: SupportingAgentRequest) -> SupportingRunResponse:
    names = selected_agent_names(request.selected_categories)
    response = SupportingRunResponse(activated_agents=names)
    if not names:
        response.warnings.append("No Supporting Agent was activated because no gap category was selected")
        return response

    with ThreadPoolExecutor(max_workers=min(request.max_workers, len(names))) as executor:
        futures = {executor.submit(AGENT_CLASSES[name].run, request): name for name in names}
        for future in as_completed(futures):
            name = futures[future]
            try:
                output = future.result()
            except Exception as exc:
                output = SupportingAgentOutput(
                    agent_name=name,
                    status="FAILED",
                    errors=[f"Supporting agent future failed safely: {exc.__class__.__name__}"],
                    partial=True,
                )
            response.outputs.append(output)
            response.warnings.extend(output.warnings)
            response.errors.extend(output.errors)
    response.outputs.sort(key=lambda item: item.agent_name.value)
    response.partial = bool(response.errors or any(output.partial for output in response.outputs))
    return response
