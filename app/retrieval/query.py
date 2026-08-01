from __future__ import annotations

from typing import List

from .models import RetrievalRequest


def generate_queries(request: RetrievalRequest) -> List[str]:
    role = request.target_role.strip() or request.intent.strip()
    location = f" {request.location.strip()}" if request.location.strip() else ""
    queries = list(request.explicit_queries)
    queries.extend([
        f"{role}{location} 채용 공고",
        f"{role}{location} required skills hiring",
        f"{role}{location} 지원 자격 마감일",
    ])
    if request.preparation_period:
        queries.append(f"{role} 준비 기간 채용 요구사항 {request.preparation_period}")
    return list(dict.fromkeys(query.strip() for query in queries if query.strip()))


def contradiction_queries(request: RetrievalRequest) -> List[str]:
    claim = request.contradiction_claim or request.intent
    role = request.target_role or request.intent
    return list(dict.fromkeys([
        f"{role} {claim} 반대 근거",
        f"{role} {claim} correction contradiction",
        f"{claim} official source update",
    ]))
