from __future__ import annotations

import io
import re
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

try:
    from pypdf import PdfReader
except ImportError:  # pragma: no cover
    PdfReader = None

from .models import (
    MetadataItem,
    NormalizedMetadata,
    PreferenceInformation,
    Provenance,
    RawExtraction,
)


MAX_PDF_BYTES = 10 * 1024 * 1024

SECTION_RULES: Sequence[Tuple[str, Sequence[str]]] = (
    ("education_and_training", ("education", "academic", "학력", "교육")),
    ("research", ("research", "publication", "publications", "연구", "논문")),
    ("activities_and_career_experience", ("experience", "career", "activities", "경력", "활동")),
    ("internships", ("internship", "intern", "인턴")),
    ("projects", ("project", "projects", "프로젝트")),
    ("technical_skills", ("technical skills", "skills", "기술 역량", "기술스택", "skills")),
    ("language_proficiency", ("language", "languages", "언어", "어학")),
    ("leadership_and_contribution", ("leadership", "leadership & activities", "리더십", "대외활동")),
    ("volunteering_and_contribution", ("volunteer", "service", "봉사", "기여")),
    ("awards", ("award", "awards", "honor", "honors", "수상", "수상경력")),
    ("certifications_and_credentials", ("certification", "certificate", "credentials", "자격", "자격증", "수료")),
)

NOISE_PATTERNS = (
    re.compile(r"^\[Page\s+\d+\]$", re.I),
    re.compile(r"^\s*(?:page\s*)?\d+\s*$", re.I),
    re.compile(r"^\s*(?:19|20)\d{2}\s*(?:년|[-/.])?\s*(?:현재|present|[-/.])?\s*$", re.I),
    re.compile(r"^\s*(?:https?://|www\.)", re.I),
    re.compile(r"^\s*(?:linkedin|github)\s*$", re.I),
    re.compile(r"^[+()0-9 .-]{7,}$"),
)

CONTACT_PATTERN = re.compile(
    r"(?:[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}|(?:\+?\d[\d ()-]{7,}\d)|linkedin|github\.com)",
    re.I,
)


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

def _clean_line(value: str) -> str:
    value = value.replace("\u00a0", " ")
    value = re.sub(r"[\t ]+", " ", value)
    value = re.sub(r"^[\-\u2022\u25aa\u25cf\u25e6*]+\s*", "", value)
    return value.strip(" |")


def _normalized_heading(value: str) -> str:
    value = _clean_line(value).lower()
    value = re.sub(r"[:：]+$", "", value).strip()
    value = re.sub(r"[^a-z0-9가-힣& ]+", " ", value)
    return re.sub(r"\s+", " ", value).strip()


def _section_for_heading(value: str) -> Optional[str]:
    heading = _normalized_heading(value)
    if not heading or len(heading) > 48:
        return None
    for category, candidates in SECTION_RULES:
        for candidate in candidates:
            candidate_heading = _normalized_heading(candidate)
            if heading == candidate_heading or heading.startswith(candidate_heading + " "):
                return category
    return None


def _is_noise(value: str) -> bool:
    value = _clean_line(value)
    if not value:
        return True
    if any(pattern.search(value) for pattern in NOISE_PATTERNS):
        return True
    if CONTACT_PATTERN.search(value) and len(value) < 180:
        return True
    return False


def _looks_like_bullet(value: str) -> bool:
    return bool(re.match(r"^\s*(?:[-\u2022\u25aa\u25cf\u25e6*]|\d+[.)])\s+", value))


def _looks_like_new_entry(value: str, category: str) -> bool:
    if _looks_like_bullet(value):
        return True
    if category in {"education_and_training", "internships", "activities_and_career_experience"}:
        if re.search(r"(?:대학교|대학원|연구소|lab|주식회사|회사|인턴|튜터|창업자|developer|consulting)", value, re.I):
            return True
    if category in {"projects", "research"}:
        if re.search(r"(?:https?://|github|icml|neurips|aaai|publication|논문|프로젝트)", value, re.I):
            return True
    return False


def _page_for_text(page_text: List[Dict[str, object]], source_text: str) -> Optional[int]:
    first_line = _clean_line(source_text.splitlines()[0]) if source_text else ""
    if not first_line:
        return None
    for page in page_text:
        if first_line.lower() in str(page.get("text", "")).lower():
            return int(page["page"])
    return None


def _split_page_sections(raw: RawExtraction) -> List[Tuple[str, str, Optional[int]]]:
    sections: List[Tuple[str, str, Optional[int]]] = []
    current_category = "additional_information"
    current_lines: List[str] = []
    current_page: Optional[int] = None

    def flush() -> None:
        nonlocal current_lines, current_page
        if current_lines:
            source = "\n".join(current_lines).strip()
            if source:
                sections.append((current_category, source, current_page))
        current_lines = []
        current_page = None

    for page in raw.page_text:
        page_number = int(page["page"])
        for raw_line in str(page.get("text", "")).splitlines():
            line = _clean_line(raw_line)
            if not line:
                continue
            heading_category = _section_for_heading(line)
            if heading_category:
                flush()
                current_category = heading_category
                continue
            if _is_noise(line):
                continue
            if current_page is None:
                current_page = page_number
            current_lines.append(line)
    flush()
    return sections


def _merge_section_lines(category: str, source: str) -> List[Tuple[str, str]]:
    lines = [_clean_line(line) for line in source.splitlines() if _clean_line(line)]
    if not lines:
        return []

    entries: List[List[str]] = []
    for line in lines:
        if not entries or _looks_like_new_entry(line, category):
            entries.append([line])
        else:
            previous = entries[-1][-1]
            should_join = (
                len(line) < 120
                or previous.endswith((".", ":", "。", "다", "함"))
                or category in {"education_and_training", "internships"}
            )
            if should_join:
                entries[-1].append(line)
            else:
                entries.append([line])

    result = []
    for entry in entries:
        original = "\n".join(entry).strip()
        normalized = re.sub(r"\s+", " ", " ".join(entry)).strip()
        if len(normalized) >= 3:
            result.append((original, normalized))
    return result


def normalize_extraction(
    raw: RawExtraction,
    preferred_role: str = "",
    preparation_period: str = "",
    additional_information: str = "",
) -> NormalizedMetadata:
    items: List[MetadataItem] = []
    warnings = list(raw.warnings)
    sections = _split_page_sections(raw)

    for category, source, page in sections:
        for original, normalized in _merge_section_lines(category, source):
            if category == "additional_information":
                warnings.append("Unlabeled CV text was retained as additional information for user review")
            items.append(
                MetadataItem(
                    category=category,
                    normalized_value=normalized,
                    original_text=original,
                    source_page=page or _page_for_text(raw.page_text, original),
                    provenance=Provenance.CV_EXTRACTED,
                    extraction_confidence=0.65 if category != "additional_information" else 0.4,
                )
            )

    if not items:
        warnings.append("No structured CV items were extracted; user input is required")

    if additional_information.strip():
        items.append(
            MetadataItem(
                category="additional_information",
                normalized_value=_clean_line(additional_information),
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
