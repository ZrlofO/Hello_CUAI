from __future__ import annotations

import io
import re
from pathlib import Path
from typing import Dict, List, Tuple

try:
    from pypdf import PdfReader
except ImportError:  # pragma: no cover - exercised in environments before dependency installation
    PdfReader = None

from .models import (
    MetadataItem,
    NormalizedMetadata,
    PreferenceInformation,
    Provenance,
    RawExtraction,
)


MAX_PDF_BYTES = 10 * 1024 * 1024
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


def validate_pdf(filename: str, content_type: str, pdf_bytes: bytes) -> None:
    if not filename.lower().endswith(".pdf"):
        raise ValueError("Only PDF files are supported")
    if content_type and content_type.lower() not in {"application/pdf", "application/octet-stream"}:
        raise ValueError("The uploaded file must have PDF MIME type")
    if not pdf_bytes:
        raise ValueError("The uploaded PDF is empty")
    if len(pdf_bytes) > MAX_PDF_BYTES:
        raise ValueError(f"The uploaded PDF exceeds the {MAX_PDF_BYTES // (1024 * 1024)}MB limit")
    if not pdf_bytes.startswith(b"%PDF-"):
        raise ValueError("The uploaded file is not a valid PDF signature")


def extract_pdf(pdf_bytes: bytes, filename: str, content_type: str) -> RawExtraction:
    validate_pdf(filename, content_type, pdf_bytes)
    if PdfReader is None:
        raise RuntimeError("PDF extraction requires pypdf. Install dependencies from requirements.txt")

    try:
        reader = PdfReader(io.BytesIO(pdf_bytes), strict=False)
    except Exception as exc:
        raise ValueError("The PDF could not be opened or is malformed") from exc

    if reader.is_encrypted:
        try:
            decrypted = reader.decrypt("")
        except Exception:
            decrypted = 0
        if not decrypted:
            raise ValueError("Password-protected PDFs are not supported")

    page_text: List[Dict[str, object]] = []
    warnings: List[str] = []
    for page_number, page in enumerate(reader.pages, start=1):
        try:
            text = (page.extract_text() or "").strip()
        except Exception:
            text = ""
            warnings.append(f"Text extraction failed on page {page_number}")
        page_text.append({"page": page_number, "text": text})

    extracted_text = "\n\n".join(
        f"[Page {page['page']}]\n{page['text']}" for page in page_text if page["text"]
    ).strip()
    if not extracted_text:
        warnings.append("No selectable text was found; the PDF may be image-only")

    return RawExtraction(
        filename=Path(filename).name,
        content_type=content_type or "application/pdf",
        byte_size=len(pdf_bytes),
        page_count=len(page_text),
        extracted_text=extracted_text,
        page_text=page_text,
        extraction_method="pypdf",
        warnings=warnings,
    )


def _category_for_line(line: str) -> str:
    lowered = line.lower()
    rules = [
        ("awards", ["award", "honor", "수상", "장학"]),
        ("leadership_and_contribution", ["leadership", "leader", "회장", "대표", "리더"]),
        ("volunteering_and_contribution", ["volunteer", "봉사", "community", "community"]),
        ("language_proficiency", ["language", "english", "한국어", "toeic", "ielts", "언어"]),
        ("certifications_and_credentials", ["certification", "certificate", "자격", "license", "자격증"]),
        ("research", ["research", "publication", "논문", "연구"]),
        ("internships", ["intern", "인턴"]),
        ("competitions", ["competition", "hackathon", "contest", "공모전", "해커톤"]),
        ("technical_skills", ["skills", "python", "java", "react", "sql", "tensorflow", "pytorch"]),
        ("education_and_training", ["education", "university", "bachelor", "master", "학력", "교육"]),
        ("projects", ["project", "프로젝트"]),
        ("activities_and_career_experience", ["experience", "career", "work", "경력", "활동"]),
    ]
    for category, keywords in rules:
        if any(keyword in lowered for keyword in keywords):
            return category
    return "additional_information"


def _page_for_text(page_text: List[Dict[str, object]], line: str) -> int | None:
    for page in page_text:
        if line and line.lower() in str(page.get("text", "")).lower():
            return int(page["page"])
    return None


def normalize_extraction(
    raw: RawExtraction,
    preferred_role: str = "",
    preparation_period: str = "",
    additional_information: str = "",
) -> NormalizedMetadata:
    items: List[MetadataItem] = []
    warnings = list(raw.warnings)
    lines = [re.sub(r"^[-•▪*\s]+", "", line).strip() for line in raw.extracted_text.splitlines()]
    lines = [line for line in lines if line and not re.fullmatch(r"\[Page \d+\]", line)]

    for line in lines:
        if len(line) < 2:
            continue
        category = _category_for_line(line)
        items.append(
            MetadataItem(
                category=category,
                normalized_value=line,
                original_text=line,
                source_page=_page_for_text(raw.page_text, line),
                provenance=Provenance.CV_EXTRACTED,
                extraction_confidence=0.45,
            )
        )

    if not items:
        warnings.append("No structured CV items were extracted; user input is required")

    if additional_information.strip():
        items.append(
            MetadataItem(
                category="additional_information",
                normalized_value=additional_information.strip(),
                original_text=additional_information.strip(),
                provenance=Provenance.USER_PROVIDED,
                extraction_confidence=1.0,
            )
        )

    confidence = sum(item.extraction_confidence for item in items) / len(items) if items else 0.0
    return NormalizedMetadata(
        items=items,
        preferences=PreferenceInformation(
            preferred_role=preferred_role.strip(),
            preparation_period=preparation_period.strip(),
            additional_information=additional_information.strip(),
        ),
        warnings=warnings,
        extraction_confidence=round(confidence, 3),
    )
