from __future__ import annotations

import json
import os
import re
import urllib.request
from typing import Any, Dict, List, Optional

from .models import MetadataItem, NormalizedMetadata, PreferenceInformation, Provenance, RawExtraction


OPENAI_ENDPOINT = "https://api.openai.com/v1/responses"
ALLOWED_CATEGORIES = {
    "activities_and_career_experience",
    "awards",
    "leadership_and_contribution",
    "volunteering_and_contribution",
    "language_proficiency",
    "certifications_and_credentials",
    "projects",
    "research",
    "internships",
    "competitions",
    "technical_skills",
    "education_and_training",
    "additional_information",
}


def _response_text(payload: Dict[str, Any]) -> str:
    if isinstance(payload.get("output_text"), str):
        return payload["output_text"]
    chunks: List[str] = []
    for output in payload.get("output", []) or []:
        for content in output.get("content", []) or []:
            if isinstance(content, dict) and isinstance(content.get("text"), str):
                chunks.append(content["text"])
    return "\n".join(chunks)


def _parse_json(text: str) -> Dict[str, Any]:
    text = text.strip()
    text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text, flags=re.I | re.S)
    try:
        value = json.loads(text)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", text, flags=re.S)
        if not match:
            raise ValueError("LLM metadata rephrase response was not JSON")
        value = json.loads(match.group(0))
    if not isinstance(value, dict):
        raise ValueError("LLM metadata rephrase response must be an object")
    return value


def _source_contains(raw: RawExtraction, source_page: int, original_text: str) -> bool:
    if not source_page or source_page > raw.page_count or not original_text.strip():
        return False
    page = next((item for item in raw.page_text if int(item.get("page", 0)) == source_page), None)
    if not page:
        return False
    normalize = lambda value: re.sub(r"\s+", " ", value).strip().lower()
    return normalize(original_text) in normalize(str(page.get("text", "")))


def _build_prompt(raw: RawExtraction, preferred_role: str, preparation_period: str) -> str:
    pages = [{"page": item.get("page"), "text": item.get("text", "")} for item in raw.page_text]
    return json.dumps(
        {
            "task": "Convert the CV into concise, reviewable normalized metadata.",
            "language": "Korean when the source is Korean; preserve technical names and proper nouns.",
            "target_role": preferred_role,
            "preparation_period": preparation_period,
            "rules": [
                "Do not transcribe every line.",
                "Group each experience, research item, education item, project, skill group, or activity into a meaningful item.",
                "Rewrite normalized_value as one concise factual sentence or keyword group.",
                "Return keywords separately when they improve search or downstream matching.",
                "Do not invent metrics, dates, outcomes, institutions, titles, or skills.",
                "original_text must be copied from the supplied page text exactly enough for provenance validation.",
                "source_page must be the page containing original_text.",
                "Exclude contact details, URLs, section headings, page numbers, and isolated dates.",
            ],
            "categories": sorted(ALLOWED_CATEGORIES),
            "output_schema": {
                "items": [
                    {
                        "category": "one category",
                        "normalized_value": "concise rephrased factual value",
                        "keywords": ["short factual keyword"],
                        "original_text": "verbatim source excerpt",
                        "source_page": 1,
                        "confidence": 0.0,
                    }
                ],
                "warnings": ["string"],
            },
            "pages": pages,
        },
        ensure_ascii=False,
    )


def rephrase_metadata(
    raw: RawExtraction,
    preferred_role: str = "",
    preparation_period: str = "",
) -> Optional[NormalizedMetadata]:
    api_key = os.getenv("OPENAI_API_KEY", "").strip()
    enabled = os.getenv("METADATA_REPHRASE_ENABLED", "true").lower() not in {"0", "false", "no"}
    if not enabled or not api_key:
        return None

    model = os.getenv("OPENAI_MODEL", "gpt-5.6-luna")
    body = json.dumps(
        {
            "model": model,
            "input": [
                {
                    "role": "system",
                    "content": "You are a provenance-preserving CV metadata normalization agent. Return JSON only. Never invent facts.",
                },
                {"role": "user", "content": _build_prompt(raw, preferred_role, preparation_period)},
            ],
            "max_output_tokens": int(os.getenv("METADATA_REPHRASE_MAX_OUTPUT_TOKENS", "3500")),
        },
        ensure_ascii=False,
    ).encode("utf-8")
    request = urllib.request.Request(
        OPENAI_ENDPOINT,
        data=body,
        method="POST",
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
    )
    with urllib.request.urlopen(request, timeout=float(os.getenv("METADATA_REPHRASE_TIMEOUT_SECONDS", "45"))) as response:
        payload = json.loads(response.read().decode("utf-8"))
    result = _parse_json(_response_text(payload))

    items: List[MetadataItem] = []
    warnings = list(raw.warnings) + [str(item) for item in result.get("warnings", []) if item]
    for candidate in result.get("items", []) or []:
        if not isinstance(candidate, dict):
            warnings.append("A malformed LLM metadata item was discarded")
            continue
        category = str(candidate.get("category", "additional_information"))
        original_text = str(candidate.get("original_text", "")).strip()
        normalized_value = str(candidate.get("normalized_value", "")).strip()
        try:
            source_page = int(candidate.get("source_page"))
        except (TypeError, ValueError):
            source_page = 0
        if category not in ALLOWED_CATEGORIES or not normalized_value or not _source_contains(raw, source_page, original_text):
            warnings.append("An LLM metadata item failed category or provenance validation and was discarded")
            continue
        confidence = min(max(float(candidate.get("confidence", 0.0)), 0.0), 0.8)
        keywords = [str(value).strip() for value in candidate.get("keywords", []) if str(value).strip()]
        items.append(
            MetadataItem(
                category=category,
                normalized_value=normalized_value,
                keywords=keywords[:12],
                original_text=original_text,
                source_page=source_page,
                provenance=Provenance.CV_EXTRACTED,
                extraction_confidence=confidence,
            )
        )

    if not items:
        raise ValueError("LLM metadata rephrase returned no provenance-valid items")
    confidence = sum(item.extraction_confidence for item in items) / len(items)
    return NormalizedMetadata(
        items=items,
        preferences=PreferenceInformation(
            preferred_role=preferred_role.strip(),
            preparation_period=preparation_period.strip(),
        ),
        warnings=warnings,
        extraction_confidence=round(confidence, 3),
        normalization_method="llm_rephrased_with_provenance_validation",
        rephrasing_model=model,
    )
