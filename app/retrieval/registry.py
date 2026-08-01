from __future__ import annotations

import json
import os
from typing import Dict, List, Optional

from pydantic import BaseModel, Field, validator


class SourcePolicy(BaseModel):
    name: str
    publisher: str
    source_type: str = "UNKNOWN"
    domains: List[str] = Field(default_factory=list)
    enabled: bool = True
    quality_threshold: float = Field(default=0.4, ge=0.0, le=1.0)
    allow_snippet_only: bool = False
    requires_original_page: bool = True

    @validator("name", "publisher")
    def required_value(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("source policy name and publisher are required")
        return value


class SourceRegistry(BaseModel):
    sources: List[SourcePolicy] = Field(default_factory=list)

    def get(self, name: str) -> Optional[SourcePolicy]:
        return next((source for source in self.sources if source.name == name), None)

    def enabled(self, names: Optional[List[str]] = None) -> List[SourcePolicy]:
        selected = set(names or [])
        return [
            source for source in self.sources
            if source.enabled and (not selected or source.name in selected)
        ]


def default_source_registry() -> SourceRegistry:
    defaults = [
        SourcePolicy(name="work24", publisher="Work24", source_type="GOVERNMENT", domains=["work24.go.kr"], quality_threshold=0.8),
        SourcePolicy(name="saramin", publisher="Saramin", source_type="SECONDARY_SUMMARY", domains=["saramin.co.kr"]),
        SourcePolicy(name="jobkorea", publisher="JobKorea", source_type="SECONDARY_SUMMARY", domains=["jobkorea.co.kr"]),
    ]
    raw = os.getenv("RETRIEVAL_SOURCE_REGISTRY", "").strip()
    if not raw:
        return SourceRegistry(sources=defaults)
    try:
        configured = json.loads(raw)
        return SourceRegistry.model_validate(configured)
    except Exception:
        return SourceRegistry(sources=defaults)
