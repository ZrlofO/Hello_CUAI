from __future__ import annotations

import hashlib
import re
import urllib.error
import urllib.request
from datetime import date, datetime, timedelta, timezone
from html import unescape
from typing import Callable, Dict, Iterable, List, Optional, Protocol, Tuple
from urllib.parse import urldefrag, urlparse

from app.evidence.ledger import EvidenceLedger
from app.evidence.models import Evidence, EvidenceStatus, SourceType

from .models import RetrievalRequest, RetrievalResponse, RetrievedPage, SearchResult
from .query import contradiction_queries, generate_queries
from .registry import SourcePolicy, SourceRegistry


class SearchProvider(Protocol):
    def search(self, query: str, limit: int) -> Iterable[SearchResult]: ...


PageFetcher = Callable[[str], Tuple[int, str, str]]


def canonical_url(url: str) -> str:
    url, _ = urldefrag(url.strip())
    parsed = urlparse(url)
    path = parsed.path.rstrip("/") or "/"
    return f"{parsed.scheme.lower()}://{parsed.netloc.lower()}{path}"


def deduplicate_results(results: Iterable[SearchResult]) -> List[SearchResult]:
    seen = set()
    unique = []
    for result in results:
        key = canonical_url(result.url) or hashlib.sha256(result.title.lower().encode()).hexdigest()
        if key in seen:
            continue
        seen.add(key)
        unique.append(result)
    return unique


def default_page_fetcher(url: str) -> Tuple[int, str, str]:
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0 HICAREER/1.0",
            "Accept": "text/html,application/xhtml+xml,text/plain;q=0.8,*/*;q=0.5",
        },
    )
    with urllib.request.urlopen(request, timeout=8) as response:
        content_type = response.headers.get_content_type()
        raw = response.read(2_000_000)
        return response.status, content_type, raw.decode("utf-8", errors="replace")


def clean_page_text(value: str) -> str:
    value = unescape(re.sub(r"<[^>]+>", " ", value))
    return re.sub(r"\s+", " ", value).strip()


def extract_relevant_passage(text: str, query: str, max_length: int = 1200) -> str:
    cleaned = clean_page_text(text)
    if not cleaned:
        return ""
    terms = [term.lower() for term in re.findall(r"[\w가-힣+#.-]{2,}", query) if len(term) > 1]
    lower = cleaned.lower()
    positions = [lower.find(term) for term in terms if lower.find(term) >= 0]
    center = min(positions) if positions else 0
    start = max(0, center - 240)
    return cleaned[start:start + max_length]


def extract_date(value: str) -> Optional[date]:
    patterns = [
        r"(20\d{2})[./-](\d{1,2})[./-](\d{1,2})",
        r"(20\d{2})년\s*(\d{1,2})월\s*(\d{1,2})일",
    ]
    for pattern in patterns:
        match = re.search(pattern, value)
        if match:
            try:
                return date(int(match.group(1)), int(match.group(2)), int(match.group(3)))
            except ValueError:
                continue
    return None


def extract_publication_date(text: str, fallback: Optional[date] = None) -> Optional[date]:
    match = re.search(r"(?:published|posted|등록일|게시일|공고일)\s*[:：]?\s*([^|,;]+)", text, re.I)
    return extract_date(match.group(1)) if match else fallback


def extract_deadline(text: str) -> Optional[date]:
    match = re.search(r"(?:deadline|마감일|접수기간|지원기간|~)\s*[:：]?\s*([^|;]+)", text, re.I)
    if not match:
        return None
    return extract_date(match.group(1))


def determine_active_status(deadline: Optional[date], text: str, today: Optional[date] = None) -> Optional[bool]:
    today = today or date.today()
    if deadline:
        return deadline >= today
    if re.search(r"(?:마감|closed|expired|종료)", text, re.I):
        return False
    if re.search(r"(?:상시채용|채용시까지|open|active)", text, re.I):
        return True
    return None


def freshness_score(publication_date: Optional[date], today: Optional[date] = None) -> float:
    today = today or date.today()
    if not publication_date:
        return 0.0
    age = max(0, (today - publication_date).days)
    return round(max(0.0, 1.0 - min(age, 730) / 730), 3)


class RetrievalPipeline:
    def __init__(
        self,
        registry: SourceRegistry,
        providers: Dict[str, SearchProvider],
        page_fetcher: PageFetcher = default_page_fetcher,
    ):
        self.registry = registry
        self.providers = providers
        self.page_fetcher = page_fetcher

    def run(self, request: RetrievalRequest, ledger: Optional[EvidenceLedger] = None) -> Tuple[RetrievalResponse, EvidenceLedger]:
        ledger = ledger or EvidenceLedger()
        queries = generate_queries(request)
        contradiction = contradiction_queries(request)
        response = RetrievalResponse(request=request, queries=queries, contradiction_queries=contradiction)
        results: List[SearchResult] = []
        for policy in self.registry.enabled(request.source_names):
            provider = self.providers.get(policy.name)
            if not provider:
                response.warnings.append(f"No provider configured for source: {policy.name}")
                continue
            for query in queries:
                try:
                    results.extend(provider.search(query, request.limit))
                except (TimeoutError, urllib.error.URLError, OSError) as exc:
                    response.warnings.append(f"Source {policy.name} unavailable: {exc.__class__.__name__}")
                except Exception as exc:
                    response.warnings.append(f"Source {policy.name} failed safely: {exc.__class__.__name__}")
        results = deduplicate_results(results)[:request.limit]
        response.search_results = results

        for result in results:
            policy = self.registry.get(result.source_name)
            if not policy:
                response.warnings.append(f"Result source policy missing: {result.source_name}")
                continue
            page = self._retrieve_page(result, policy, request.intent)
            response.pages.append(page)
            if page.retrieval_error or page.restricted:
                continue
            evidence = Evidence(
                source_type=SourceType(policy.source_type) if policy.source_type in SourceType._value2member_map_ else SourceType.UNKNOWN,
                source_url=result.url,
                source_title=page.title or result.title,
                publisher=policy.publisher,
                publication_date=page.publication_date or result.publication_date,
                application_deadline=page.application_deadline,
                active_status_verified=page.active_status,
                relevant_excerpt=page.relevant_passage,
                normalized_fact=None,
                freshness_score=freshness_score(page.publication_date or result.publication_date),
                relevance_score=1.0 if page.relevant_passage else 0.0,
                support_status=EvidenceStatus.UNVERIFIED,
                retrieval_query=result.query,
                retrieved_by_node="internet_retrieval",
                verification_status=EvidenceStatus.UNVERIFIED,
            )
            self._apply_policy_filter(evidence, policy, response)
            ledger.add_evidence(evidence)
            if evidence.verification_status != EvidenceStatus.REJECTED:
                response.evidence_ids.append(evidence.evidence_id)
        validation = ledger.validate()
        response.warnings.extend(validation.warnings)
        response.errors.extend(validation.errors)
        return response, ledger

    def _apply_policy_filter(self, evidence: Evidence, policy: SourcePolicy, response: RetrievalResponse) -> None:
        EvidenceLedger.apply_deterministic_scores(evidence)
        if evidence.source_quality_score < policy.quality_threshold:
            evidence.verification_status = EvidenceStatus.REJECTED
            evidence.rejection_reason = (
                f"source_quality_score {evidence.source_quality_score:.3f} "
                f"is below policy threshold {policy.quality_threshold:.3f}"
            )
            response.warnings.append(f"Rejected low-quality evidence from source: {policy.name}")

    def _retrieve_page(self, result: SearchResult, policy: SourcePolicy, query: str) -> RetrievedPage:
        try:
            status, content_type, body = self.page_fetcher(result.url)
            if status in {401, 403, 407, 429}:
                return RetrievedPage(url=result.url, title=result.title, status_code=status, restricted=True, retrieval_error="access_restricted")
            if status >= 400:
                return RetrievedPage(url=result.url, title=result.title, status_code=status, retrieval_error=f"http_{status}")
            text = clean_page_text(body)
            passage = extract_relevant_passage(text, query)
            publication = extract_publication_date(text, result.publication_date)
            deadline = extract_deadline(text)
            active = determine_active_status(deadline, text)
            return RetrievedPage(
                url=result.url,
                title=result.title,
                text=text[:5000],
                relevant_passage=passage,
                status_code=status,
                publication_date=publication,
                application_deadline=deadline,
                active_status=active,
            )
        except (TimeoutError, urllib.error.URLError, OSError) as exc:
            return RetrievedPage(url=result.url, title=result.title, retrieval_error=exc.__class__.__name__)
        except Exception as exc:
            return RetrievedPage(url=result.url, title=result.title, retrieval_error=f"page_parse_{exc.__class__.__name__}")
