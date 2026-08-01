from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict
from uuid import uuid4

from .metadata.models import WorkflowState


def build_metadata_handoff_discussion(workflow: WorkflowState) -> Dict[str, Any]:
    metadata = workflow.user_confirmed_metadata or workflow.normalized_metadata
    role = metadata.preferences.preferred_role or "목표 직무 미입력"
    period = metadata.preferences.preparation_period or "준비 기간 미입력"
    item_count = len(metadata.items)
    timestamp = datetime.now(timezone.utc).isoformat()

    return {
        "status": "PHASE_1_HANDOFF",
        "source": "confirmed_metadata",
        "warnings": [
            "Phase 1에서는 market research와 Supporting Agent 실행을 아직 시작하지 않았습니다.",
            "아래 메시지는 확정 metadata handoff 상태이며 외부 사실이나 추천이 아닙니다.",
        ],
        "discussionHistory": [
            {
                "event_id": str(uuid4()),
                "speaker": "Leading Agent 1 · Applicant Profile",
                "role": "confirmed metadata handoff",
                "tone": "profile",
                "status": "COMPLETED",
                "message": f"확정된 지원자 프로필을 전달합니다. 목표 직무는 '{role}', 준비 기간은 '{period}', 확정 metadata 항목은 {item_count}개입니다.",
                "evidence_refs": [item.item_id for item in metadata.items],
                "created_at": timestamp,
            },
            {
                "event_id": str(uuid4()),
                "speaker": "Leading Agent 2 · Market Fit Strategy",
                "role": "next-stage handoff",
                "tone": "strategy",
                "status": "PENDING",
                "message": "확정 metadata를 수신했습니다. 다음 단계에서만 현재 채용시장 evidence를 조회하고, source quality와 freshness 검증 후 gap을 선택해야 합니다.",
                "evidence_refs": [],
                "created_at": timestamp,
            },
            {
                "event_id": str(uuid4()),
                "speaker": "Supporting Agents",
                "role": "activation decision",
                "tone": "question",
                "status": "PENDING",
                "message": "Consulting Agent의 evidence-backed gap selection이 완료되기 전까지 전문 agent는 실행하지 않습니다.",
                "evidence_refs": [],
                "created_at": timestamp,
            },
        ],
    }
