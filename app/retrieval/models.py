from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Any, Dict, List, Optional
from uuid import uuid4

from pydantic import BaseModel, Field, validator


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class RetrievalRequest(BaseModel):
    intent: str
    target_role: str = ""
    location: str = ""
    preparation_period: str = ""
    explicit_queries: List[str] = Field(default_factory=list)
    limit: int = Field(default=10, ge=1, le=50)
    source_names: List[str] = Field(default_factory=list)
    contradiction_claim: Optional[str] = None

    @validator("intent")
    def intent_required(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("retrieval intent must not be empty")
        return value


class SearchResult(BaseModel):
    result_id: str = Field(default_factory=lambda: f"res_{uuid4().hex}")
    source_name: str
    title: str
    url: str
    snippet: str = ""
    publisher: Optional[str] = None
    publication_date: Optional[date] = None
    query: str
    retrieved_at: datetime = Field(default_factory=utc_now)
    is_snippet_only: bool = True

    @validator("url")
    def http_url(cls, value: str) -> str:
        if not value.lower().startswith(("http://", "https://")):
            raise ValueError("search result URL must use http(s)")
        return value


class RetrievedPage(BaseModel):
    url: str
    title: str = ""
    text: str = ""
    relevant_passage: str = ""
    status_code: Optional[int] = None
    publication_date: Optional[date] = None
    application_deadline: Optional[date] = None
    active_status: Optional[bool] = None
    retrieval_error: Optional[str] = None
    restricted: bool = False
    retrieved_at: datetime = Field(default_factory=utc_now)


class RetrievalResponse(BaseModel):
    request: RetrievalRequest
    queries: List[str] = Field(default_factory=list)
    contradiction_queries: List[str] = Field(default_factory=list)
    search_results: List[SearchResult] = Field(default_factory=list)
    pages: List[RetrievedPage] = Field(default_factory=list)
    evidence_ids: List[str] = Field(default_factory=list)
    warnings: List[str] = Field(default_factory=list)
    errors: List[str] = Field(default_factory=list)
    completed_at: datetime = Field(default_factory=utc_now)
