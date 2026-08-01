import base64
import html
import json
import math
import mimetypes
import os
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Lock
from xml.etree import ElementTree

from dotenv import load_dotenv

load_dotenv()

ROOT = Path(__file__).resolve().parent
HOST = os.getenv("HOST", "0.0.0.0")
PORT = int(os.getenv("PORT", "8080"))
WORK24_AUTH_KEY = os.getenv("WORK24_AUTH_KEY", "")
WORK24_ENDPOINT = "https://www.work24.go.kr/cm/openApi/call/wk/callOpenApiSvcInfo210L01.do"
CACHE_TTL_SECONDS = int(os.getenv("JOBS_CACHE_TTL_SECONDS", "600"))
DEFAULT_JOB_KEYWORD = os.getenv("JOB_SEARCH_KEYWORD", "신입 채용")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-5.6-luna")
FAST_AGENT_MODE = os.getenv("HICAREER_FAST_MODE", "1") != "0"
SEARCH_CACHE_TTL = int(os.getenv("HICAREER_SEARCH_CACHE_TTL", "900"))
SEARCH_CACHE = {}
OPENAI_ENDPOINT = "https://api.openai.com/v1/responses"
AGENT_PROMPT_DIR = ROOT / "agent_prompts"
RETRIEVAL_SOURCE_REGISTRY_PATH = ROOT / "retrieval_source_registry.json"
DEBUG_DIR = ROOT / "debug"
SUPPORTING_SEARCH_LIMIT_PER_AGENT = 8
CONSULT_SUCCESS_CASE_LIMIT = 10

_cache = {}

FALLBACK_JOBS = [
    {
        "title": "Junior AI Engineer",
        "company": "헬스케어 AI 스타트업",
        "category": "unclassified",
        "location": "서울 · 하이브리드",
        "deadline": "D-9",
        "fit": 94,
        "skills": [],
        "reason": "프로젝트·논문·해커톤 경험을 강점으로 가져가기 좋은 공고",
        "url": "diagnosis.html",
    },
    {
        "title": "Frontend Developer Intern",
        "company": "B2B SaaS 기업",
        "category": "unclassified",
        "location": "판교 · 인턴",
        "deadline": "D-12",
        "fit": 89,
        "skills": [],
        "reason": "배포 프로젝트와 GitHub 증거를 보여주기 좋은 포지션",
        "url": "diagnosis.html",
    },
    {
        "title": "Data Analyst Assistant",
        "company": "커머스 플랫폼",
        "category": "unclassified",
        "location": "서울 · 신입",
        "deadline": "D-15",
        "fit": 86,
        "skills": [],
        "reason": "정량 성과와 문제 정의 역량을 만들기 좋은 공고",
        "url": "diagnosis.html",
    },
    {
        "title": "Product Manager Intern",
        "company": "모바일 서비스 스타트업",
        "category": "unclassified",
        "location": "서울 · 인턴",
        "deadline": "D-7",
        "fit": 82,
        "skills": [],
        "reason": "대외활동·운영 경험을 프로덕트 언어로 바꾸기 좋음",
        "url": "diagnosis.html",
    },
    {
        "title": "Backend Developer Rookie",
        "company": "핀테크 플랫폼",
        "category": "unclassified",
        "location": "서울 · 신입",
        "deadline": "D-18",
        "fit": 80,
        "skills": [],
        "reason": "서버 프로젝트와 장애 해결 경험을 강조하기 좋은 공고",
        "url": "diagnosis.html",
    },
    {
        "title": "Growth Marketer Intern",
        "company": "에듀테크 기업",
        "category": "unclassified",
        "location": "원격 가능",
        "deadline": "D-21",
        "fit": 77,
        "skills": [],
        "reason": "캠페인·대외활동 경험을 수치 성과로 확장하기 좋음",
        "url": "diagnosis.html",
    },
]


def text_of(item, *names):
    for name in names:
        node = item.find(name)
        if node is not None and node.text:
            return node.text.strip()
    return ""


def normalize_deadline(close_date):
    if not close_date:
        return "상시"
    digits = "".join(char for char in close_date if char.isdigit())
    if len(digits) == 8:
        return f"~{digits[4:6]}.{digits[6:8]}"
    return close_date


def clean_text(value):
    value = re.sub(r"<[^>]+>", " ", value)
    value = html.unescape(value)
    value = re.sub(r"([a-z])([A-Z])", r"\1 \2", value)
    value = re.sub(r"([A-Z]{2,})([A-Z][a-z])", r"\1 \2", value)
    value = re.sub(r"([A-Za-z])([0-9])", r"\1 \2", value)
    value = re.sub(r"([0-9])([A-Za-z])", r"\1 \2", value)
    value = re.sub(r"\s+", " ", value)
    return value.strip(" -|\n\t")


def absolute_url(base_url, href):
    return urllib.parse.urljoin(base_url, html.unescape(href))


def read_url(url, timeout=6):
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0 HICAREER/1.0",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "ko-KR,ko;q=0.9,en;q=0.7",
        },
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return response.read().decode("utf-8", errors="replace")


def strip_tags(value):
    value = re.sub(r"<(script|style|svg|noscript)[^>]*>[\s\S]*?</\1>", " ", value or "", flags=re.IGNORECASE)
    return clean_text(re.sub(r"<[^>]+>", " ", value))


def cached_read_url(url, timeout=4):
    key = (url, timeout)
    now = time.time()
    cached = SEARCH_CACHE.get(key)
    if cached and now - cached[0] < SEARCH_CACHE_TTL:
        return cached[1]
    html_text = read_url(url, timeout=timeout)
    SEARCH_CACHE[key] = (now, html_text)
    return html_text


def write_debug_json(filename, payload):
    DEBUG_DIR.mkdir(parents=True, exist_ok=True)
    path = DEBUG_DIR / filename
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return str(path)


def load_retrieval_source_registry():
    try:
        return json.loads(RETRIEVAL_SOURCE_REGISTRY_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {"source_registry": [], "priority_policy": {}}


def extract_page_title(html_text):
    match = re.search(r"<title[^>]*>(.*?)</title>", html_text or "", re.IGNORECASE | re.DOTALL)
    return strip_tags(match.group(1)) if match else ""


def extract_relevant_excerpt(html_text, keywords, limit=320):
    text = strip_tags(html_text)
    if not text:
        return ""
    lowered = text.lower()
    normalized_keywords = [clean_text(keyword).lower() for keyword in keywords if clean_text(keyword)]
    positions = [lowered.find(keyword) for keyword in normalized_keywords if lowered.find(keyword) >= 0]
    if positions:
        start = max(0, min(positions) - 80)
        return text[start:start + limit]
    return text[:limit]


def extract_links_from_page(base_url, html_text, allowed_domains, keywords, limit=8):
    links = []
    seen = set()
    for match in re.finditer(r'<a[^>]+href=["\'](?P<href>[^"\']+)["\'][^>]*>(?P<label>.*?)</a>', html_text or "", re.IGNORECASE | re.DOTALL):
        href = absolute_url(base_url, match.group("href"))
        href = href.split("#", 1)[0]
        if not href.startswith(("http://", "https://")) or href in seen:
            continue
        if not url_in_allowed_domains(href, allowed_domains):
            continue
        label = strip_tags(match.group("label"))
        haystack = f"{label} {href}".lower()
        if keywords and not any(clean_text(keyword).lower() in haystack for keyword in keywords if clean_text(keyword)):
            continue
        seen.add(href)
        links.append({"title": label or href, "url": href})
        if len(links) >= limit:
            break
    return links


def build_target_role_search_terms(target_role):
    role = clean_text(target_role)
    return [role] if role else []


def read_registry_seed_candidates(source_entry, categories, assigned_gap, target_role, limit=6):
    allowed_domains = source_entry.get("allowed_domains", [])
    seed_urls = source_entry.get("seed_urls", []) or ([source_entry.get("homepage_url")] if source_entry.get("homepage_url") else [])
    keywords = [
        target_role,
        *categories,
        *summarize_text_items(assigned_gap, key="gap_name", limit=3),
        "모집",
        "채용",
        "공고",
        "접수",
        "마감",
        "자격요건",
        "우대사항",
    ]
    candidates = []
    seen = set()
    if source_entry.get("source_name") == "잡코리아" and target_role:
        for search_term in build_target_role_search_terms(target_role):
            try:
                jobs = scrape_jobkorea_jobs(search_term, limit=limit)
            except Exception:
                jobs = []
            for job in jobs:
                if job.get("url") in seen:
                    continue
                seen.add(job.get("url"))
                candidates.append(
                    {
                        "query": f"jobkorea_site_search:{search_term}",
                        "title": job.get("title", ""),
                        "url": job.get("url", ""),
                        "snippet": strip_tags(job.get("reason", "")) or "잡코리아 자체 검색 결과에서 확인한 채용 상세 공고입니다.",
                        "retrieved_at": time.strftime("%Y-%m-%d"),
                    }
                )
                if len(candidates) >= limit:
                    return candidates
    for seed_url in seed_urls[:3]:
        try:
            html_text = cached_read_url(seed_url, timeout=4)
        except Exception:
            continue
        title = extract_page_title(html_text) or source_entry.get("source_name", "")
        excerpt = extract_relevant_excerpt(html_text, keywords)
        if seed_url not in seen:
            seen.add(seed_url)
            candidates.append(
                {
                    "query": "registry_seed_page",
                    "title": title,
                    "url": seed_url,
                    "snippet": excerpt,
                    "retrieved_at": time.strftime("%Y-%m-%d"),
                }
            )
        for link in extract_links_from_page(seed_url, html_text, allowed_domains, keywords, limit=limit):
            if link["url"] in seen:
                continue
            seen.add(link["url"])
            link_title = link.get("title", "")
            link_excerpt = excerpt
            try:
                link_html = cached_read_url(link["url"], timeout=4)
                link_title = extract_page_title(link_html) or link_title
                link_excerpt = extract_relevant_excerpt(link_html, keywords)
            except Exception:
                pass
            candidates.append(
                {
                    "query": "registry_seed_link",
                    "title": link_title,
                    "url": link.get("url", ""),
                    "snippet": link_excerpt,
                    "retrieved_at": time.strftime("%Y-%m-%d"),
                }
            )
            if len(candidates) >= limit:
                return candidates
    return candidates


def is_search_redirect_url(url):
    parsed = urllib.parse.urlparse(url or "")
    host = parsed.netloc.lower()
    path = parsed.path.lower()
    return (
        "bing.com" in host and path.startswith("/ck/")
    ) or (
        "google." in host and path.startswith("/url")
    )


def url_in_allowed_domains(url, allowed_domains):
    if not allowed_domains:
        return True
    host = urllib.parse.urlparse(url or "").netloc.lower()
    return any(host == domain.lower() or host.endswith("." + domain.lower()) for domain in allowed_domains)


def registry_source_categories():
    categories = []
    for entry in load_retrieval_source_registry().get("source_registry", []):
        categories.extend(entry.get("source_category", []))
    return list(dict.fromkeys(categories))


def source_categories_from_consult_plan(assigned_gap):
    selected = []
    for gap in assigned_gap or []:
        if not isinstance(gap, dict):
            continue
        for key in ("source_categories", "retrieval_source_categories", "source_category"):
            value = gap.get(key)
            if isinstance(value, list):
                selected.extend(str(item) for item in value if item)
            elif isinstance(value, str) and value:
                selected.append(value)
    known = set(registry_source_categories())
    return [category for category in dict.fromkeys(selected) if category in known]


def select_registry_entries(categories):
    registry = load_retrieval_source_registry()
    entries = registry.get("source_registry", [])
    selected = []
    for entry in entries:
        entry_categories = set(entry.get("source_category", []))
        if entry_categories.intersection(categories):
            selected.append(entry)
    return selected


def is_landing_or_listing_candidate(result, source_entry):
    url = result.get("url", "")
    parsed = urllib.parse.urlparse(url)
    path = parsed.path.rstrip("/").lower()
    query = urllib.parse.parse_qs(parsed.query)
    homepage = (source_entry.get("homepage_url") or "").rstrip("/")
    if url.rstrip("/") == homepage:
        return True
    if result.get("query") == "registry_seed_page":
        return True
    if parsed.netloc.endswith("wevity.com") and query.get("c", [""])[0] == "find":
        return True
    if parsed.netloc.endswith("wevity.com") and query.get("c", [""])[0] == "event":
        return True
    if parsed.netloc.endswith("jobkorea.co.kr") and path.startswith("/theme/"):
        return True
    if parsed.netloc.endswith("thinkcontest.com") and path.endswith("/thinkgood/hindex.do"):
        return True
    if "search" in path or "calendar" in path:
        return True
    listing_markers = [
        "/search",
        "/recruit-home",
        "/list",
        "/calendar",
        "/zf_user/search",
        "/job_postings/search_guide",
    ]
    return any(path == marker or path.startswith(marker + "/") for marker in listing_markers)


def build_retrieval_purpose_keywords(target_role="", categories=None, assigned_gap=None):
    text = " ".join(
        [
            target_role or "",
            " ".join(summarize_text_items(assigned_gap or [], key="gap_name", limit=3)),
        ]
    )
    keywords = [token.lower() for token in re.findall(r"[A-Za-z가-힣0-9+#.]{2,}", text)]
    return list(dict.fromkeys(keywords))


def quality_gate_search_result(result, source_entry, seen_urls, purpose_keywords=None):
    url = result.get("url", "")
    title = result.get("title", "")
    snippet = result.get("snippet", "")
    allowed_domains = source_entry.get("allowed_domains", [])
    landing_or_listing = is_landing_or_listing_candidate(result, source_entry)
    haystack = f"{title} {snippet}".lower()
    purpose_keywords = [keyword.lower() for keyword in (purpose_keywords or []) if keyword]
    relevant_to_purpose = not purpose_keywords or any(keyword in haystack for keyword in purpose_keywords)
    checks = {
        "is_original_url": bool(url) and not is_search_redirect_url(url),
        "is_allowed_domain": url_in_allowed_domains(url, allowed_domains),
        "has_nonempty_snippet_or_excerpt": bool(snippet and len(snippet) >= 30),
        "is_relevant_to_search_purpose": bool(title and (snippet or not landing_or_listing) and relevant_to_purpose),
        "has_extractable_fields": bool(title and url),
        "is_landing_or_listing_page": landing_or_listing,
        "is_duplicate": url in seen_urls,
        "is_login_or_paid_only": False,
    }
    keep = (
        checks["is_original_url"]
        and checks["is_allowed_domain"]
        and checks["has_nonempty_snippet_or_excerpt"]
        and checks["is_relevant_to_search_purpose"]
        and checks["has_extractable_fields"]
        and not checks["is_landing_or_listing_page"]
        and not checks["is_duplicate"]
        and not checks["is_login_or_paid_only"]
    )
    checks["decision"] = "keep" if keep else "needs_verification" if checks["is_landing_or_listing_page"] else "discard"
    if not checks["is_original_url"]:
        checks["reason"] = "검색 엔진 redirect URL입니다."
    elif not checks["is_allowed_domain"]:
        checks["reason"] = "source registry의 allowed_domains에 포함되지 않습니다."
    elif checks["is_landing_or_listing_page"]:
        checks["reason"] = "서비스 메인/목록/seed 페이지라 최종 추천 source로 확정하지 않았습니다."
    elif checks["is_duplicate"]:
        checks["reason"] = "중복 URL입니다."
    elif not checks["has_nonempty_snippet_or_excerpt"]:
        checks["reason"] = "원문에서 충분한 excerpt를 확인하지 못했습니다."
    elif not checks["has_extractable_fields"]:
        checks["reason"] = "제목 또는 URL 등 필수 필드를 확인하지 못했습니다."
    elif not checks["is_relevant_to_search_purpose"]:
        checks["reason"] = "target_role 또는 assigned_gap과 직접 관련된 근거를 확인하지 못했습니다."
    else:
        checks["reason"] = "source registry와 검색 목적 기준을 통과했습니다." if keep else "검색 목적과의 관련성이 부족합니다."
    return checks


def infer_used_for_from_categories(categories):
    category_set = set(categories or [])
    if category_set.intersection({"job_posting", "entry_level_job", "internship"}):
        return "benchmark"
    if category_set.intersection({"competition", "external_activity", "team_recruiting", "certificate_exam", "language_test"}):
        return "recommendation"
    if category_set.intersection({"company_info", "company_review", "salary_reference", "interview_reference"}):
        return "company_reference"
    if category_set.intersection({"test_schedule", "registration_period", "score_release_date"}):
        return "exam_schedule"
    return "recommendation"


def build_verified_retrieval_sources(agent_key, preferences, assigned_gap):
    target_role = preferences.get("target_role", "") if isinstance(preferences, dict) else ""
    categories = source_categories_from_consult_plan(assigned_gap) or registry_source_categories()
    entries = select_registry_entries(categories)
    raw_candidates = []
    verified_sources = []
    discarded_sources = []
    seen_urls = set()
    for source_entry in entries[:4]:
        source_categories = [category for category in source_entry.get("source_category", []) if category in categories] or source_entry.get("source_category", [])[:2]
        purpose_keywords = build_retrieval_purpose_keywords(target_role, source_categories, assigned_gap)
        seed_results = read_registry_seed_candidates(source_entry, source_categories, assigned_gap, target_role, limit=4)
        for result in seed_results:
            candidate = {
                "source_name": source_entry.get("source_name", ""),
                "title": result.get("title", ""),
                "url": result.get("url", ""),
                "query": result.get("query", "registry_seed_page"),
                "snippet": result.get("snippet", ""),
                "retrieved_at": result.get("retrieved_at", time.strftime("%Y-%m-%d")),
            }
            raw_candidates.append(candidate)
            gate = quality_gate_search_result(result, source_entry, seen_urls, purpose_keywords=purpose_keywords)
            if gate["decision"] == "keep":
                seen_urls.add(result.get("url", ""))
                related_gap = ", ".join(summarize_text_items(assigned_gap, key="gap_name", limit=2))
                verified_sources.append(
                    {
                        "source_name": source_entry.get("source_name", ""),
                        "source_category": source_categories[0] if source_categories else "",
                        "title": result.get("title", ""),
                        "url": result.get("url", ""),
                        "retrieved_at": result.get("retrieved_at", time.strftime("%Y-%m-%d")),
                        "extracted_fields": {
                            "snippet": result.get("snippet", ""),
                            "query": result.get("query", "registry_seed_page"),
                        },
                        "used_for": infer_used_for_from_categories(source_categories),
                        "related_gap": related_gap,
                        "status_note": "source registry seed page 또는 allowed domain retrieval 기준으로 1차 검증했습니다. 최종 지원 전 원문 페이지 확인이 필요합니다.",
                        "source_quality_gate": gate,
                    }
                )
            else:
                discarded_sources.append(
                    {
                        "title": result.get("title", ""),
                        "url": result.get("url", ""),
                        "discard_reason": gate.get("reason", "source quality gate를 통과하지 못했습니다."),
                        "source_quality_gate": gate,
                    }
                )
            if len(verified_sources) >= SUPPORTING_SEARCH_LIMIT_PER_AGENT:
                return {
                    "raw_search_candidates": raw_candidates,
                    "verified_sources": verified_sources,
                    "discarded_sources": discarded_sources,
                }
    return {
        "raw_search_candidates": raw_candidates,
        "verified_sources": verified_sources,
        "discarded_sources": discarded_sources,
    }


def collect_consulting_success_cases(target_role):
    cases = []
    seen_urls = set()
    registry = load_retrieval_source_registry()
    preferred_categories = {"career_community", "self_introduction_reference", "interview_reference", "company_review"}
    entries = [
        entry for entry in registry.get("source_registry", [])
        if preferred_categories.intersection(set(entry.get("source_category", [])))
    ]
    for entry in entries:
        source_categories = [category for category in entry.get("source_category", []) if category in preferred_categories]
        purpose_keywords = build_retrieval_purpose_keywords(target_role, source_categories, [])
        for result in read_registry_seed_candidates(entry, source_categories, [], target_role, limit=4):
            url = result.get("url", "")
            if not url or url in seen_urls:
                continue
            gate = quality_gate_search_result(result, entry, seen_urls, purpose_keywords=purpose_keywords)
            if gate.get("decision") != "keep":
                continue
            seen_urls.add(url)
            cases.append(
                {
                    "source_type": "public_success_case_or_resume_reference",
                    "source_name": entry.get("source_name", ""),
                    "title": result.get("title", ""),
                    "url": url,
                    "snippet": result.get("snippet", ""),
                    "query": result.get("query", "registry_seed_page"),
                    "retrieved_at": result.get("retrieved_at", time.strftime("%Y-%m-%d")),
                    "source_quality_gate": gate,
                    "note": "source registry의 커뮤니티/자기소개서/면접 참고 source에서 확인한 공개 참고 후보입니다. 본문 검증 전에는 확정 사실로 사용하지 않습니다.",
                }
            )
            if len(cases) >= CONSULT_SUCCESS_CASE_LIMIT:
                return cases
    return cases


def build_supporting_search_results(agent_key, preferences, assigned_gap):
    return build_verified_retrieval_sources(agent_key, preferences, assigned_gap)


def extract_deadline(text_block):
    patterns = [
        r'D-\s*\d+',
        r'~\s*\d{1,2}\.\d{1,2}\([^)]*\)',
        r'~\s*\d{1,2}\.\d{1,2}',
        r'오늘마감|내일마감|상시채용|채용시',
    ]
    for pattern in patterns:
        match = re.search(pattern, text_block)
        if match:
            return clean_text(match.group(0))
    return "상세 확인"


def extract_location(text_block):
    regions = [
        "서울", "경기", "인천", "부산", "대구", "대전", "광주", "울산", "세종",
        "강원", "충북", "충남", "전북", "전남", "경북", "경남", "제주", "원격",
    ]
    match = re.search(r'(' + '|'.join(regions) + r')[가-힣\w\s·,-]{0,24}', text_block)
    if match:
        return clean_text(match.group(0))
    return "지역 확인"


def extract_summary(text_block, title, company):
    cleaned = clean_text(text_block)
    cleaned = cleaned.replace(title, " ").replace(company, " ")
    parts = [part.strip() for part in re.split(r'\s{2,}|\||•|·', cleaned) if part.strip()]
    blocked = ["스크랩", "관심기업", "입사지원", "홈페이지 지원", "즉시지원", "공고 보기"]
    useful = []
    for part in parts:
        if any(word in part for word in blocked):
            continue
        if re.fullmatch(r'D-\s*\d+|~?\d{1,2}\.\d{1,2}.*|\d+분 전.*|\d+일 전.*', part):
            continue
        if 4 <= len(part) <= 90:
            useful.append(part)
    return " · ".join(useful[:2])


def extract_context(html_text, start, end):
    return html_text[max(0, start - 900):min(len(html_text), end + 1200)]


def build_web_job(title, company, url, source, rank, context=""):
    context_text = clean_text(context)
    summary = extract_summary(context, title, company)
    return {
        "title": title or "채용 공고",
        "company": company or source,
        "category": "unclassified",
        "location": extract_location(context_text),
        "deadline": extract_deadline(context_text),
        "fit": max(72, 92 - rank * 3),
        "skills": [],
        "reason": summary,
        "url": url,
        "source": source,
    }


def extract_company_near(html_text, start, end):
    before = html_text[max(0, start - 900):start]
    after = html_text[end:min(len(html_text), end + 900)]
    candidates = []
    for pattern in [
        r'class="[^"]*(?:company|corp|name)[^"]*"[^>]*>(.*?)</',
        r'<a[^>]+href="[^"]*(?:company|corp)[^"]*"[^>]*>(.*?)</a>',
        r'<span[^>]*>([^<>]{2,40}(?:주식회사|\(주\)|㈜|유한회사|그룹|테크|랩스|코리아)[^<>]*)</span>',
    ]:
        candidates.extend(clean_text(match) for match in re.findall(pattern, before + after, re.I | re.S))
    return next((candidate for candidate in candidates if candidate and len(candidate) <= 45), "")


def first_match(pattern, text_block):
    match = re.search(pattern, text_block, re.I | re.S)
    if not match:
        return ""
    return clean_text(match.group(1))


def all_matches(pattern, text_block):
    return [clean_text(match) for match in re.findall(pattern, text_block, re.I | re.S) if clean_text(match)]


def scrape_saramin_jobs(keyword, limit):
    query = urllib.parse.urlencode({"searchType": "search", "searchword": keyword})
    base_url = "https://www.saramin.co.kr"
    url = f"{base_url}/zf_user/search/recruit?{query}"
    html_text = read_url(url)
    jobs = []
    seen = set()
    blocks = re.findall(r'<div class="item_recruit"[\s\S]*?(?=<div class="item_recruit"|<div class="common_recruilt_list|$)', html_text)

    for block in blocks:
        link_match = re.search(r'<a[^>]+href="([^"]*(?:/zf_user/jobs/relay/view|/zf_user/jobs/relay/pop-view)[^"]*)"[^>]*(?:title="([^"]+)")?[^>]*>(.*?)</a>', block, re.I | re.S)
        if not link_match:
            continue

        href, title_attr, raw_title = link_match.groups()
        title = clean_text(title_attr or raw_title)
        if len(title) < 4 or title in seen or "스크랩" in title:
            continue

        company = first_match(r'<strong class="corp_name">[\s\S]*?<a[^>]*>(.*?)</a>', block) or extract_company_near(block, 0, len(block))
        deadline = first_match(r'<span class="date">(.*?)</span>', block) or extract_deadline(clean_text(block))
        condition_match = re.search(r'<div class="job_condition">([\s\S]*?)</div>', block, re.I | re.S)
        condition_block = condition_match.group(1) if condition_match else ""
        condition_spans = all_matches(r'<span>([\s\S]*?)</span>', condition_block)
        sectors = all_matches(r'<div class="job_sector">([\s\S]*?)</div>', block)
        condition_text = " ".join(condition_spans) or clean_text(condition_block)
        sector_text = clean_text(" ".join(sectors))
        location = condition_spans[0] if condition_spans else extract_location(condition_text)
        summary_parts = []
        if condition_text:
            summary_parts.append(condition_text)
        if sector_text:
            summary_parts.append(sector_text.replace("등록일", " 등록일"))
        summary = " · ".join(part for part in summary_parts if part)[:140]

        seen.add(title)
        job = build_web_job(title, company, absolute_url(base_url, href), "사람인", len(jobs), block)
        job["deadline"] = deadline
        job["location"] = location
        job["reason"] = summary
        job["skills"] = []
        jobs.append(job)
        if len(jobs) >= limit:
            break
    return jobs


def scrape_jobkorea_jobs(keyword, limit):
    query = urllib.parse.urlencode({"stext": keyword})
    base_url = "https://www.jobkorea.co.kr"
    url = f"{base_url}/Search/?{query}"
    html_text = read_url(url)
    jobs = []
    seen = set()

    for match in re.finditer(r'<a[^>]+href="([^"]*(?:/Recruit/GI_Read|/Recruit/Co_Read|/List_GI/)[^"]*)"[^>]*>(.*?)</a>', html_text, re.I | re.S):
        href, raw_title = match.groups()
        title = clean_text(raw_title)
        if len(title) < 4 or title in seen or "즉시지원" in title:
            continue
        seen.add(title)
        context = extract_context(html_text, *match.span())
        company = extract_company_near(html_text, *match.span())
        jobs.append(build_web_job(title, company, absolute_url(base_url, href), "잡코리아", len(jobs), context))
        if len(jobs) >= limit:
            break
    return jobs


def merge_jobs(*job_groups, limit):
    merged = []
    seen = set()
    for group in job_groups:
        for job in group:
            key = f"{job.get('title')}|{job.get('company')}"
            if key in seen:
                continue
            seen.add(key)
            merged.append(job)
            if len(merged) >= limit:
                return merged
    return merged


def normalize_work24_item(item):
    title = text_of(item, "title", "wantedTitle", "recrutPbancTtl") or "채용 공고"
    company = text_of(item, "company", "corpNm", "instNm", "empBusiNm") or "기업명 미공개"
    location = text_of(item, "region", "workRegion", "basicAddr", "workPlc") or "지역 미정"
    close_date = text_of(item, "closeDt", "receiptCloseDt", "pbancEndYmd")
    url = text_of(item, "wantedInfoUrl", "detailUrl", "url") or "diagnosis.html"
    return {
        "title": title,
        "company": company,
        "category": "unclassified",
        "location": location,
        "deadline": normalize_deadline(close_date),
        "fit": 78,
        "skills": [],
        "reason": "현재 채용 시장에서 요구되는 역량을 CV와 비교해보기 좋은 공고",
        "url": url,
    }


def parse_work24_xml(xml_text, limit):
    root = ElementTree.fromstring(xml_text)
    items = root.findall(".//wanted") or root.findall(".//item")
    jobs = [normalize_work24_item(item) for item in items[:limit]]
    return jobs


def fetch_popular_jobs(limit, keyword=DEFAULT_JOB_KEYWORD):
    cache_key = f"web:{keyword}:{limit}"
    cached = _cache.get(cache_key)
    if cached and time.time() - cached["saved_at"] < CACHE_TTL_SECONDS:
        return cached["jobs"][:limit]

    web_jobs = merge_jobs(
        scrape_saramin_jobs(keyword, limit),
        scrape_jobkorea_jobs(keyword, limit),
        limit=limit,
    )
    if web_jobs:
        _cache[cache_key] = {"saved_at": time.time(), "jobs": web_jobs}
        return web_jobs[:limit]

    return fetch_work24_jobs(limit)


def fetch_work24_jobs(limit):
    cache_key = f"work24:{limit}"
    cached = _cache.get(cache_key)
    if cached and time.time() - cached["saved_at"] < CACHE_TTL_SECONDS:
        return cached["jobs"][:limit]

    if not WORK24_AUTH_KEY:
        return FALLBACK_JOBS[:limit]

    params = urllib.parse.urlencode(
        {
            "authKey": WORK24_AUTH_KEY,
            "callTp": "L",
            "returnType": "XML",
            "startPage": "1",
            "display": str(min(max(limit, 1), 20)),
        }
    )
    request = urllib.request.Request(f"{WORK24_ENDPOINT}?{params}", headers={"User-Agent": "HICAREER/1.0"})

    with urllib.request.urlopen(request, timeout=5) as response:
        xml_text = response.read().decode("utf-8", errors="replace")

    jobs = parse_work24_xml(xml_text, limit)
    if not jobs:
        return FALLBACK_JOBS[:limit]

    _cache[cache_key] = {"saved_at": time.time(), "jobs": jobs}
    return jobs[:limit]



def parse_multipart(body, content_type):
    boundary_match = re.search(r"boundary=([^;]+)", content_type)
    if not boundary_match:
        return {}, {}
    boundary = boundary_match.group(1).strip().strip('"').encode()
    fields = {}
    files = {}
    for part in body.split(b"--" + boundary):
        part = part.strip(b"\r\n")
        if not part or part == b"--" or b"\r\n\r\n" not in part:
            continue
        header_bytes, value = part.split(b"\r\n\r\n", 1)
        headers = header_bytes.decode("utf-8", errors="replace")
        name_match = re.search(r'name="([^"]+)"', headers)
        if not name_match:
            continue
        name = name_match.group(1)
        filename_match = re.search(r'filename="([^"]*)"', headers)
        value = value.rstrip(b"\r\n")
        if filename_match and filename_match.group(1):
            files[name] = {"filename": filename_match.group(1), "content": value}
        else:
            fields[name] = value.decode("utf-8", errors="replace")
    return fields, files


def tokenize(text):
    return [token.lower() for token in re.findall(r"[A-Za-z][A-Za-z0-9+#.]{1,}|[가-힣]{2,}", text)]


STOPWORDS = {
    "and", "or", "the", "a", "an", "to", "of", "in", "on", "for", "with", "by", "from", "as", "at", "is", "are",
    "my", "our", "your", "their", "this", "that", "these", "those", "using", "used", "based", "across", "including",
    "experience", "candidate", "present", "expected", "advisor", "author", "authors", "abstract", "email", "phone",
    "kyuan", "oh", "kyuanoh", "chung", "ang", "university", "cau", "cuai", "seoul", "korea", "bumsoo", "kim",
    "award", "paper", "summer", "winter", "conference", "proceedings", "equal", "contribution", "correspondingauthor",
    "under", "review", "submitted", "proceedingsofthe", "th",
    "서울", "경기", "강남구", "영등포구", "성남시", "분당구", "경력무관", "학력무관", "대졸", "계약직", "인턴직", "정규직", "등록일", "수정일", "채용", "공고",
    "시스템통합", "솔루션업체", "전자상거래", "데이터마이닝", "데이터시각화", "앱개발",
}

PHRASE_ALIASES = {
    "vision language": "vision-language",
    "vision language models": "vision-language models",
    "large vision language models": "large vision-language models",
    "open source": "open-source",
    "artificial intelligence": "artificial intelligence",
    "machine learning": "machine learning",
    "deep learning": "deep learning",
}


def normalize_phrase(phrase):
    phrase = clean_text(phrase).lower()
    phrase = phrase.replace("–", "-").replace("—", "-")
    phrase = re.sub(r"[^a-z0-9가-힣+#.\-\s]", " ", phrase)
    phrase = re.sub(r"\s+", " ", phrase).strip()
    return PHRASE_ALIASES.get(phrase, phrase)


def split_glued_function_words(token):
    token = re.sub(r"(diagnosis|distillation|representation|processing|grounding)(and|via|with|for|from|to)$", r"\1 \2", token)
    token = re.sub(r"(research|candidate|developed|designed|conducted)(in|on|for|with)$", r"\1 \2", token)
    return token.split()


def phrase_tokens(text):
    raw_tokens = tokenize(text)
    tokens = []
    for token in raw_tokens:
        tokens.extend(split_glued_function_words(token))
    return [
        token
        for token in tokens
        if token not in STOPWORDS
        and not token.isdigit()
        and 1 < len(token) <= 28
        and not re.fullmatch(r"[a-z]*[0-9][a-z0-9]*", token)
    ]


def extract_keyphrases(text, top_n=12):
    tokens = phrase_tokens(text)
    scores = {}
    for size in (1, 2, 3):
        for index in range(0, max(0, len(tokens) - size + 1)):
            phrase = normalize_phrase(" ".join(tokens[index:index + size]))
            if not phrase or phrase in STOPWORDS:
                continue
            parts = phrase.split()
            if any(part in STOPWORDS for part in parts):
                continue
            if re.search(r"시스템통합|솔루션업체|전자상거래|영등포구|강남구|성남시|분당구", phrase):
                continue
            if "java" in parts and "python" in parts:
                continue
            if "si" in parts:
                continue
            if len(set(parts)) < len(parts):
                continue
            if size == 1 and len(phrase) <= 2:
                continue
            length_bonus = 1 + (size - 1) * 0.55
            scores[phrase] = scores.get(phrase, 0) + length_bonus

    ranked = sorted(scores.items(), key=lambda item: (item[1], len(item[0])), reverse=True)
    selected = []
    for phrase, score in ranked:
        if any(phrase != chosen and phrase in chosen for chosen in selected):
            continue
        selected.append(phrase)
        if len(selected) >= top_n:
            break
    return selected


def overlap_phrases(left, right):
    left_set = set(left)
    right_set = set(right)
    exact = left_set & right_set
    fuzzy = set()
    for left_phrase in left_set:
        for right_phrase in right_set:
            if left_phrase == right_phrase:
                continue
            if len(left_phrase) >= 5 and len(right_phrase) >= 5 and (left_phrase in right_phrase or right_phrase in left_phrase):
                fuzzy.add(left_phrase if len(left_phrase) <= len(right_phrase) else right_phrase)
    return list(exact | fuzzy)


def evidence_signals(cv_text):
    signals = []
    compact = compact_text(cv_text)
    checks = [
        ("research intern", "리서치 인턴"),
        ("publication", "논문/출판"),
        ("accepted", "논문 accept"),
        ("conference", "학회"),
        ("award", "수상"),
        ("prize", "대회 수상"),
        ("hackathon", "해커톤"),
        ("leaderboard", "리더보드 성과"),
        ("president", "리더십"),
        ("scholarship", "장학"),
        ("github", "GitHub"),
        ("open source", "오픈소스"),
        ("kaist", "KAIST 연구 경험"),
    ]
    for keyword, label in checks:
        if compact_text(keyword) in compact:
            signals.append(label)
    return list(dict.fromkeys(signals))

def compact_text(text):
    return re.sub(r"[^a-z0-9가-힣]+", "", text.lower())


def keyword_matches(text, keyword):
    lowered = text.lower()
    normalized_keyword = keyword.lower()
    compact = compact_text(text)
    compact_keyword = compact_text(keyword)

    if re.fullmatch(r"[a-z0-9+#.]{1,3}", normalized_keyword):
        return re.search(rf"(?<![a-z0-9]){re.escape(normalized_keyword)}(?![a-z0-9])", lowered) is not None

    return normalized_keyword in lowered or bool(compact_keyword and compact_keyword in compact)


def vectorize(text):
    vector = {}
    for token in tokenize(text):
        vector[token] = vector.get(token, 0) + 1
    return vector


def cosine_similarity(left, right):
    if not left or not right:
        return 0.0
    dot = sum(value * right.get(key, 0) for key, value in left.items())
    left_norm = math.sqrt(sum(value * value for value in left.values()))
    right_norm = math.sqrt(sum(value * value for value in right.values()))
    if not left_norm or not right_norm:
        return 0.0
    return dot / (left_norm * right_norm)


def extract_profile_skills(text):
    return extract_keyphrases(text, top_n=8)


def job_document(job):
    return " ".join(
        str(value)
        for value in [
            job.get("title", ""),
            job.get("company", ""),
            job.get("location", ""),
            job.get("deadline", ""),
            job.get("reason", ""),
            " ".join(job.get("skills", [])),
        ]
    )


def clean_requirement_phrase(phrase):
    text = re.sub(r"\s+", " ", str(phrase or "")).strip(" `·,-")
    noisy_terms = ["서울", "경기", "부산", "강남구", "해운대구", "분당구", "정규직", "계약직", "인턴", "경력", "학력", "기간제", "무기계약직"]
    if len(text) < 3 or any(term in text for term in noisy_terms):
        return ""
    return text


def explain_job_fit(matched_phrases, missing_phrases, similarity, job=None):
    job = job or {}
    title = job.get("title", "해당 공고")
    company = job.get("company", "회사")
    matched = [clean_requirement_phrase(item) for item in matched_phrases]
    missing = [clean_requirement_phrase(item) for item in missing_phrases]
    matched = [item for item in matched if item][:4]
    missing = [item for item in missing if item][:3]

    reasons = []
    if matched:
        reasons.append(f"{company}의 {title}는 {', '.join(matched[:3])} 경험을 앞세워 연결할 수 있습니다.")
    elif similarity > 0.18:
        reasons.append(f"{company} 공고의 업무 방향과 CV의 전체 연구·프로젝트 맥락이 일부 맞닿아 있습니다.")
    else:
        reasons.append(f"{company} 공고는 현재 CV와 직접 겹치는 표현이 많지 않아, 지원한다면 직무 관련 경험을 선별해 재구성해야 합니다.")

    gaps = []
    if missing:
        gaps.append(f"지원 전 {', '.join(missing[:2])}와 연결되는 프로젝트 결과·사용 도구·본인 기여를 한 문단으로 보강하세요.")
    gaps.append("채용 담당자가 바로 확인할 수 있도록 대표 프로젝트 링크, 실험 지표, 역할 범위를 함께 정리하세요.")
    return reasons[:2], gaps[:2]


def rank_jobs_for_cv(cv_text, jobs, target_role):
    cv_vector = vectorize(f"{target_role} {cv_text}")
    cv_phrases = extract_keyphrases(cv_text, top_n=24)
    ranked = []
    for job in jobs:
        document = job_document(job)
        job_vector = vectorize(document)
        job_phrases = extract_keyphrases(document, top_n=14)
        matched_phrases = overlap_phrases(cv_phrases, job_phrases)
        missing_phrases = [phrase for phrase in job_phrases if phrase not in matched_phrases]
        similarity = cosine_similarity(cv_vector, job_vector)
        overlap = len(matched_phrases) / max(len(job_phrases), 1)
        title_bonus = 0.12 if target_role and any(token in document.lower() for token in tokenize(target_role)) else 0
        score = round(min(98, max(45, 56 + similarity * 58 + overlap * 30 + title_bonus * 100)))
        reasons, gaps = explain_job_fit(matched_phrases, missing_phrases, similarity, job)
        ranked_job = dict(job)
        ranked_job["fit"] = score
        ranked_job["similarity"] = round(similarity, 3)
        ranked_job["skills"] = job_phrases[:5]
        ranked_job["matchedSkills"] = matched_phrases[:6]
        ranked_job["missingSkills"] = missing_phrases[:5]
        ranked_job["fitReasons"] = reasons
        ranked_job["gaps"] = gaps
        ranked.append(ranked_job)
    return sorted(ranked, key=lambda item: item["fit"], reverse=True)


def build_cv_summary(cv_text, target_role):
    keyphrases = extract_keyphrases(cv_text, top_n=14)
    signals = evidence_signals(cv_text)
    strength_items = []
    if any(term in cv_text.lower() for term in ["publication", "accepted", "conference", "논문", "학회"]):
        strength_items.append("논문·학회 성과를 통해 연구 역량을 외부 결과로 보여줄 수 있습니다.")
    if any(term in cv_text.lower() for term in ["intern", "research intern", "인턴", "lab"]):
        strength_items.append("연구실·인턴 경험을 목표 직무의 실무형 경험으로 연결할 수 있습니다.")
    if any(term in cv_text.lower() for term in ["award", "scholarship", "수상", "장학"]):
        strength_items.append("수상·장학 이력이 있어 성과를 검증받은 경험으로 제시할 수 있습니다.")
    if not strength_items and keyphrases:
        strength_items.append("입력된 경험에서 목표 직무와 연결할 수 있는 핵심 역량이 확인됩니다.")

    return {
        "targetRole": target_role or "목표 직무 미입력",
        "extractedCharacters": len(cv_text),
        "skills": keyphrases,
        "evidenceSignals": signals,
        "strengths": strength_items,
        "gaps": ["대표 경험마다 본인 역할, 사용 기술, 결과 지표, 확인 가능한 링크를 더 선명하게 정리하면 좋습니다."],
    }


def count_keyword_hits(text, keywords):
    return sum(1 for keyword in keywords if keyword_matches(text, keyword))

OPPORTUNITY_LIBRARY = [
    {
        "title": "AI 해커톤 또는 공모전 참가",
        "source": "링커리어/위비티 검색 추천",
        "category": "hackathon",
        "duration": "1~3주",
        "deadline": "현재 모집 확인",
        "covers": ["agent", "ai", "python", "model", "evaluation", "hackathon", "공모전"],
        "impact": "외부 검증과 팀 협업 증거를 빠르게 만들 수 있습니다.",
        "url": "https://linkareer.com/list/contest",
    },
    {
        "title": "오픈소스 PR 1개 만들기",
        "source": "GitHub",
        "category": "opensource",
        "duration": "3~7일",
        "deadline": "상시",
        "covers": ["github", "open-source", "code", "python", "api", "react"],
        "impact": "코드 구현력과 외부 협업 증거를 동시에 보강합니다.",
        "url": "https://github.com/explore",
    },
    {
        "title": "RAG/Agent 미니 프로젝트 배포",
        "source": "개인 프로젝트",
        "category": "project",
        "duration": "1~2주",
        "deadline": "상시",
        "covers": ["llm", "agent", "rag", "api", "deployment", "evaluation"],
        "impact": "AI 인턴 공고에서 자주 요구되는 실전 구현 증거를 만들 수 있습니다.",
        "url": "plan.html",
    },
    {
        "title": "Kaggle/데이콘 데이터 분석 제출",
        "source": "데이콘/Kaggle",
        "category": "data",
        "duration": "1~3주",
        "deadline": "현재 대회 확인",
        "covers": ["data", "sql", "python", "benchmark", "performance", "analysis"],
        "impact": "정량 지표와 리더보드 성과를 CV에 추가하기 좋습니다.",
        "url": "https://dacon.io/competitions",
    },
    {
        "title": "직무 연계 봉사/멘토링 활동",
        "source": "1365/VMS",
        "category": "service",
        "duration": "주 2~4시간",
        "deadline": "현재 모집 확인",
        "covers": ["leadership", "communication", "education", "mentoring", "community"],
        "impact": "조직 기여와 커뮤니케이션 증거가 부족할 때만 추천합니다.",
        "url": "https://www.1365.go.kr/vols/main.do",
    },
]


def common_job_requirements(ranked_jobs, top_n=10):
    scores = {}
    for job in ranked_jobs[:8]:
        document = job_document(job)
        for phrase in extract_keyphrases(document, top_n=10):
            scores[phrase] = scores.get(phrase, 0) + 1 + job.get("fit", 0) / 100
    return [phrase for phrase, _ in sorted(scores.items(), key=lambda item: item[1], reverse=True)[:top_n]]


def detect_evidence_gaps(cv_phrases, common_requirements, evidence):
    matched = overlap_phrases(cv_phrases, common_requirements)
    gaps = [requirement for requirement in common_requirements if requirement not in matched]
    evidence_gap = []
    if not any(signal in evidence for signal in ["GitHub", "오픈소스"]):
        evidence_gap.append("코드/오픈소스 증거")
    if not any(signal in evidence for signal in ["리더보드 성과", "수상", "대회 수상"]):
        evidence_gap.append("외부 평가 성과")
    return matched, list(dict.fromkeys([*gaps[:6], *evidence_gap]))


def score_opportunity(opportunity, gaps, target_role):
    gap_text = " ".join(gaps).lower()
    role_text = target_role.lower()
    coverage = sum(1 for token in opportunity["covers"] if token.lower() in gap_text or token.lower() in role_text)
    urgency = 8 if opportunity["deadline"] != "상시" else 5
    effort = {"3~7일": 9, "1~2주": 8, "1~3주": 7, "주 2~4시간": 6}.get(opportunity["duration"], 6)
    score = min(98, 58 + coverage * 10 + urgency + effort)
    return score


def recommend_opportunities(gaps, target_role):
    ranked = []
    for opportunity in OPPORTUNITY_LIBRARY:
        item = dict(opportunity)
        item["fit"] = score_opportunity(opportunity, gaps, target_role)
        item["why"] = f"보완할 증거 `{gaps[0] if gaps else '직무 적합 증거'}`와 연결됩니다. {opportunity['impact']}"
        ranked.append(item)
    return sorted(ranked, key=lambda item: item["fit"], reverse=True)[:4]


def build_weekly_plan(opportunities, gaps):
    primary = opportunities[:2]
    actions = []
    for index, opportunity in enumerate(primary, start=1):
        actions.append(
            {
                "id": f"week-action-{index}",
                "title": opportunity["title"],
                "source": opportunity["source"],
                "duration": opportunity["duration"],
                "reason": opportunity["why"],
                "done": False,
            }
        )
    actions.append(
        {
            "id": "cv-update",
            "title": "CV 상단 3줄을 목표 공고 언어로 재작성",
            "source": "HICAREER",
            "duration": "30분",
            "reason": f"가장 큰 gap인 `{gaps[0] if gaps else '핵심 요구역량'}`를 먼저 보이게 만듭니다.",
            "done": False,
        }
    )
    return actions


def build_agent_trace(cv_text, target_role, jobs, ranked_jobs, common_requirements, gaps, opportunities):
    return [
        {"step": "CV_READ", "label": "CV PDF/입력 텍스트에서 핵심 증거 추출", "detail": f"{len(cv_text)}자 분석 완료"},
        {"step": "JOB_SEARCH", "label": "목표 직무 채용공고 검색", "detail": f"{target_role or DEFAULT_JOB_KEYWORD} 기준 {len(jobs)}개 후보 수집"},
        {"step": "RETRIEVAL", "label": "CV와 공고 문서 embedding-style ranking", "detail": f"상위 공고: {ranked_jobs[0]['title'] if ranked_jobs else '없음'}"},
        {"step": "REQUIREMENTS", "label": "상위 공고의 공통 요구 표현 추출", "detail": ", ".join(common_requirements[:4])},
        {"step": "GAP", "label": "CV에 부족한 증거 gap 탐지", "detail": ", ".join(gaps[:4]) if gaps else "큰 gap 없음"},
        {"step": "ACTION", "label": "gap을 채울 활동과 이번 주 액션 생성", "detail": f"활동 {len(opportunities)}개 추천"},
    ]


def build_agent_result(cv_text, target_role, jobs, ranked_jobs):
    cv_phrases = extract_keyphrases(cv_text, top_n=18)
    evidence = evidence_signals(cv_text)
    requirements = common_job_requirements(ranked_jobs)
    matched, gaps = detect_evidence_gaps(cv_phrases, requirements, evidence)
    opportunities = recommend_opportunities(gaps, target_role)
    weekly_plan = build_weekly_plan(opportunities, gaps)
    trace = build_agent_trace(cv_text, target_role, jobs, ranked_jobs, requirements, gaps, opportunities)
    return {
        "trace": trace,
        "cvKeyphrases": cv_phrases,
        "commonRequirements": requirements,
        "matchedEvidence": matched,
        "evidenceGaps": gaps,
        "opportunities": opportunities,
        "weeklyPlan": weekly_plan,
    }


def compact_for_prompt(value, max_chars=9000):
    value = clean_text(value)
    return value[:max_chars] + ("..." if len(value) > max_chars else "")


def response_output_text(payload):
    if isinstance(payload.get("output_text"), str):
        return payload["output_text"]
    chunks = []
    for item in payload.get("output", []):
        for content in item.get("content", []):
            if isinstance(content.get("text"), str):
                chunks.append(content["text"])
    return "\n".join(chunks)


def parse_json_object(text_value):
    try:
        return json.loads(text_value)
    except json.JSONDecodeError:
        fenced = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", text_value, re.IGNORECASE)
        if fenced:
            return json.loads(fenced.group(1))
        match = re.search(r"\{[\s\S]*\}", text_value)
        if not match:
            raise
        return json.loads(match.group(0))


def build_llm_context(cv_text, summary, ranked_jobs, agent):
    jobs_context = [
        {
            "title": job.get("title"),
            "company": job.get("company"),
            "fit": job.get("fit"),
            "deadline": job.get("deadline"),
            "location": job.get("location"),
            "source": job.get("source"),
            "jobKeyphrases": job.get("skills", []),
            "fitReasons": job.get("fitReasons", []),
            "gaps": job.get("gaps", []),
        }
        for job in ranked_jobs[:5]
    ]
    return {
        "cv_excerpt": compact_for_prompt(cv_text),
        "summary": summary,
        "ranked_jobs": jobs_context,
        "agent": {
            "cvKeyphrases": agent.get("cvKeyphrases", []),
            "commonRequirements": agent.get("commonRequirements", []),
            "matchedEvidence": agent.get("matchedEvidence", []),
            "evidenceGaps": agent.get("evidenceGaps", []),
            "opportunities": agent.get("opportunities", []),
            "weeklyPlan": agent.get("weeklyPlan", []),
        },
    }


def call_openai_llm_report(cv_text, summary, ranked_jobs, agent):
    if not OPENAI_API_KEY:
        raise ValueError("OPENAI_API_KEY가 필요합니다.")

    prompt_context = build_llm_context(cv_text, summary, ranked_jobs, agent)
    system_prompt = (
        "You are HICAREER, a Korean career-growth agent. "
        "Use only the provided CV extraction, retrieved job postings, and agent signals. "
        "Do not invent companies, awards, projects, or job requirements. "
        "Write concise Korean. Return JSON only."
    )
    user_prompt = {
        "task": "Generate a commercial-quality CV-to-job fit report and action plan. Write like a real career consultant, not a keyword matcher. For each jobFitNotes item, explain why this specific company/job is worth considering and what the applicant should supplement before applying. If company culture/success-case evidence is not provided, say the recommendation is based on the posting only; do not pretend external evidence was read.",
        "output_schema": {
            "headline": "string",
            "cvSummary": "string",
            "strengths": ["string"],
            "evidenceGaps": ["string"],
            "jobFitNotes": [{"title": "string", "fitReason": "specific Korean reason tied to company/job/posting/CV", "risk": "specific Korean preparation point before applying"}],
            "recommendedActions": [{"title": "string", "why": "string", "timeEstimate": "string"}],
            "weeklyPlan": ["string"],
            "profileUpdatePrompt": "string",
        },
        "context": prompt_context,
    }
    return call_openai_json(system_prompt, user_prompt, max_output_tokens=1600, timeout=20)


def build_deterministic_llm_report(summary, ranked_jobs, agent):
    strengths = summary.get("strengths", []) if isinstance(summary, dict) else []
    gaps = summary.get("gaps", []) if isinstance(summary, dict) else []
    if isinstance(agent, dict):
        strengths = strengths or agent.get("commonRequirements", [])[:4]
        gaps = gaps or agent.get("quickActions", [])[:4]
    job_notes = []
    for job in (ranked_jobs or [])[:4]:
        job_notes.append(
            {
                "title": job.get("title", "추천 공고"),
                "fitReason": "; ".join(job.get("fitReasons", [])[:2]) or job.get("reason", "metadata와 공고 키워드의 겹치는 지점을 기준으로 추천되었습니다."),
                "risk": "; ".join(job.get("gaps", [])[:2]) or "역할, 산출물, 정량 성과 근거를 더 보강하면 안정성이 올라갑니다.",
            }
        )
    return {
        "headline": "현재 metadata 기준으로 커리어 fit 리포트를 구성했습니다.",
        "cvSummary": summary.get("summary", "입력된 CV metadata와 추천 공고를 기준으로 강점과 보완점을 정리했습니다.") if isinstance(summary, dict) else "입력된 CV metadata와 추천 공고를 기준으로 강점과 보완점을 정리했습니다.",
        "strengths": strengths[:5] or ["CV에서 확인되는 경험을 기준으로 직무 연관 신호를 정리할 수 있습니다."],
        "evidenceGaps": gaps[:5] or ["역할, 산출물, 정량 성과, 사용 기술의 근거를 더 명확히 적으면 좋습니다."],
        "jobFitNotes": job_notes,
        "recommendedActions": [
            {
                "title": "프로젝트별 역할·산출물·성과 보강",
                "why": "단순 참여보다 본인이 만든 결과와 영향을 더 명확히 보여주는 것이 중요합니다.",
                "timeEstimate": "1~2일",
            },
            {
                "title": "목표 직무 한 줄 포지셔닝 정리",
                "why": "AI 개발, 서비스기획, AX 컨설팅 중 우선 방향이 명확해야 CV 전체 문장이 흔들리지 않습니다.",
                "timeEstimate": "30분~1시간",
            },
        ],
        "weeklyPlan": [
            "1주차: metadata에서 근거가 약한 항목을 프로젝트별로 재작성합니다.",
            "2주차: 목표 공고 5~10개와 표현을 대조해 핵심 키워드를 반영합니다.",
        ],
        "profileUpdatePrompt": "CV 상단 요약에는 목표 직무, 대표 프로젝트, 사용 기술, 확인 가능한 성과를 한 문단으로 연결해 적어주세요.",
        "fallback": True,
    }


def safe_llm_report(cv_text, summary, ranked_jobs, agent):
    try:
        report = call_openai_llm_report(cv_text, summary, ranked_jobs, agent)
        if isinstance(report, dict) and not report.get("error"):
            return report
    except Exception:
        pass
    return build_deterministic_llm_report(summary, ranked_jobs, agent)


SUPPORTING_AGENT_CONFIG = {
    "project_and_career": {
        "name": "Project & Career Experience Agent",
        "prompt_file": "project_and_career.md",
        "metadata_keys": ["projects_and_experience", "awards", "skills"],
        "benchmark_keys": ["core_requirements", "minimum_viable_profile", "strong_profile_signals", "common_rejection_risks"],
        "role": (
            "너는 Project & Career Experience Agent입니다. 프로젝트, 대외활동, 인턴, 연구, 공모전, 실무 경험을 "
            "Consult Agent가 제공한 benchmark 기준으로 검토해주세요."
        ),
        "task": (
            "활동명, 기간, 기관, 본인 역할, 수행 내용, 성과가 명확한지 확인하고, 목표 직무 기준에서 충족되는 점과 "
            "부족한 점을 준비 기간 안에서 보완 가능한 방식으로 제안해주세요."
        ),
    },
    "leadership_and_contribution": {
        "name": "Leadership & Contribution Agent",
        "prompt_file": "leadership_and_contribution.md",
        "metadata_keys": ["leadership_and_volunteering", "projects_and_experience"],
        "benchmark_keys": ["core_requirements", "common_preferred_requirements", "common_rejection_risks"],
        "role": (
            "너는 Leadership & Contribution Agent입니다. 리더십, 팀워크, 조직 경험, 봉사, 멘토링, 커뮤니티 활동이 "
            "목표 직무의 협업/소통/책임감 기준을 충족하는지 검토해주세요."
        ),
        "task": (
            "직함만 보지 말고 실제 역할, 기여, 협업 근거, 팀 규모, 기간, 의사결정 경험이 보이는지 확인해주세요."
        ),
    },
    "language_and_credential": {
        "name": "Language & Credential Agent",
        "prompt_file": "language_and_credential.md",
        "metadata_keys": ["languages_and_certificates", "skills", "projects_and_experience", "education"],
        "benchmark_keys": ["core_requirements", "common_preferred_requirements", "minimum_viable_profile", "common_rejection_risks"],
        "role": (
            "너는 Language & Credential Agent입니다. 어학, 자격증, 수료증, 교육 이수, 툴 역량이 목표 직무 기준에서 "
            "최소 검증 신호로 충분한지 검토해주세요."
        ),
        "task": (
            "명시된 어학/자격증/교육/기술만 사용하고, 자격증보다 프로젝트가 중요한 직무라면 그 점도 Consult Agent에게 알려주세요."
        ),
    },
}


def load_agent_prompt(filename):
    return (AGENT_PROMPT_DIR / filename).read_text(encoding="utf-8").strip()


LEADING_AGENT_PROMPT = load_agent_prompt("leading_agent.md")
CONSULT_AGENT_PROMPT = load_agent_prompt("consult_agent.md")
SUPPORTING_COMMON_PROMPT = load_agent_prompt("supporting_common.md")
RETRIEVAL_ONLY_PROMPT = load_agent_prompt("retrieval_only.md")
JSON_REPAIR_PROMPT = load_agent_prompt("json_repair.md")
PLANNER_AGENT_PROMPT = load_agent_prompt("planner_agent.md")


def repair_openai_json(raw_text, expected_schema, context_label="agent output"):
    system_prompt = JSON_REPAIR_PROMPT
    user_prompt = {
        "context_label": context_label,
        "expected_schema": expected_schema,
        "invalid_output": raw_text[:12000],
        "repair_rules": [
            "Preserve the original Korean content as much as possible.",
            "If a required field is missing, use an empty string, empty array, or empty object matching the schema.",
            "Return one JSON object only.",
        ],
    }
    return call_openai_json(system_prompt, user_prompt, max_output_tokens=3000, timeout=30, allow_repair=False)


def call_openai_json(system_prompt, user_prompt, max_output_tokens=1800, timeout=40, allow_repair=True):
    if not OPENAI_API_KEY:
        raise ValueError("OPENAI_API_KEY가 필요합니다.")

    request_payload = {
            "model": OPENAI_MODEL,
            "input": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": json.dumps(user_prompt, ensure_ascii=False)},
            ],
            "text": {"format": {"type": "json_object"}},
            "max_output_tokens": max_output_tokens,
    }

    def send_request(payload):
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        request = urllib.request.Request(
            OPENAI_ENDPOINT,
            data=body,
            method="POST",
            headers={
                "Authorization": f"Bearer {OPENAI_API_KEY}",
                "Content-Type": "application/json",
            },
        )
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8"))

    try:
        payload = send_request(request_payload)
    except urllib.error.HTTPError as exc:
        if exc.code not in (400, 422):
            raise
        request_payload.pop("text", None)
        payload = send_request(request_payload)
    raw_text = response_output_text(payload)
    try:
        return parse_json_object(raw_text)
    except json.JSONDecodeError:
        if not allow_repair:
            raise ValueError("LLM 응답을 JSON으로 정리하지 못했습니다.")
        try:
            return repair_openai_json(raw_text, user_prompt.get("required_output_format") or user_prompt.get("output_schema") or {}, "openai_json_response")
        except (json.JSONDecodeError, ValueError):
            raise ValueError("LLM 응답을 JSON으로 정리하지 못했습니다.")


def job_context_for_feedback(ranked_jobs):
    return [
        {
            "title": job.get("title", ""),
            "company": job.get("company", ""),
            "fit": job.get("fit", 0),
            "url": job.get("url", ""),
            "deadline": job.get("deadline", ""),
            "source": job.get("source", ""),
            "skills": job.get("skills", []),
            "fitReasons": job.get("fitReasons", []),
            "gaps": job.get("gaps", []),
        }
        for job in ranked_jobs[:10]
    ]


def build_retrieval_context(ranked_jobs, target_role):
    retrieved_at = time.strftime("%Y-%m-%d")
    benchmark_sources = []
    for job in ranked_jobs[:10]:
        benchmark_sources.append(
            {
                "source_type": "job_posting",
                "title": job.get("title", ""),
                "organization": job.get("company", ""),
                "role": target_role or job.get("title", ""),
                "url": job.get("url", ""),
                "retrieved_at": retrieved_at,
                "main_tasks": job.get("fitReasons", []),
                "required_qualifications": job.get("fitReasons", []),
                "preferred_qualifications": [],
                "required_skills": job.get("skills", []),
                "preferred_skills": [],
                "education_or_experience_requirement": "",
                "deadline": job.get("deadline", ""),
                "notes": job.get("source", ""),
            }
        )
    success_cases = collect_consulting_success_cases(target_role)
    debug_path = write_debug_json(
        "consulting_success_cases.json",
        {
            "target_role": target_role,
            "retrieved_at": retrieved_at,
            "count": len(success_cases),
            "cases": success_cases,
        },
    )
    return {
        "benchmark_sources": benchmark_sources,
        "success_case_sources": success_cases,
        "recommendation_sources": success_cases,
        "source_registry": load_retrieval_source_registry().get("source_registry", []),
        "debug_success_cases_path": debug_path,
        "retrieval_policy": "consulting_source_registry_quality_gate",
        "retrieved_at": retrieved_at,
    }


def select_retrieved_sources_for_agent(agent_key, retrieval_context, benchmark):
    job_postings = retrieval_context.get("benchmark_sources", [])
    recommendation_sources = retrieval_context.get("recommendation_sources", [])
    success_case_sources = retrieval_context.get("success_case_sources", [])
    grouped_recommendations = {}
    for item in recommendation_sources:
        grouped_recommendations.setdefault(item.get("source_type", "other"), []).append(item)

    if agent_key == "project_and_career":
        return {
            "job_postings": job_postings,
            "success_cases": success_case_sources,
            "competitions": grouped_recommendations.get("competition", []),
            "internships": grouped_recommendations.get("internship", []),
            "activities": grouped_recommendations.get("activity", []),
        }
    if agent_key == "leadership_and_contribution":
        return {
            "success_cases": success_case_sources,
            "activities": grouped_recommendations.get("activity", []),
            "volunteering": grouped_recommendations.get("volunteering", []),
            "mentoring": grouped_recommendations.get("mentoring", []),
            "team_or_community_roles": grouped_recommendations.get("team_or_community_roles", []),
        }
    if agent_key == "language_and_credential":
        return {
            "success_cases": success_case_sources,
            "certificates": grouped_recommendations.get("certificate", []),
            "language_tests": grouped_recommendations.get("language_test", []),
            "training_programs": grouped_recommendations.get("training", []),
            "job_postings": job_postings,
        }
    return {
        "job_postings": job_postings,
        "success_cases": success_case_sources,
        "benchmark": benchmark,
        "common_keywords": benchmark.get("core_requirements", []) + benchmark.get("preferred_requirements", []) + benchmark.get("common_preferred_requirements", []),
        "common_rejection_risks": benchmark.get("common_rejection_risks", []),
    }


def assigned_gaps_for_agent(agent_key, gap_analysis):
    return [
        gap for gap in gap_analysis or []
        if isinstance(gap, dict) and gap.get("assigned_agent") in (agent_key, SUPPORTING_AGENT_CONFIG.get(agent_key, {}).get("name", ""))
    ]


def summarize_text_items(items, key=None, limit=4):
    values = []
    for item in items or []:
        if isinstance(item, dict):
            value = item.get(key) if key else item.get("title") or item.get("gap") or item.get("gap_name") or item.get("missing_or_weak_point")
            if not value:
                value = " / ".join(str(v) for v in item.values() if v)[:120]
        else:
            value = str(item)
        value = clean_text(value)
        if value:
            values.append(value)
    return values[:limit]


def retrieval_counts(retrieved_sources):
    if not isinstance(retrieved_sources, dict):
        return "retrieval 자료 0개"
    parts = []
    for key, value in retrieved_sources.items():
        if isinstance(value, list):
            parts.append(f"{key} {len(value)}개")
        elif isinstance(value, dict):
            nested_count = sum(len(v) for v in value.values() if isinstance(v, list))
            parts.append(f"{key} {nested_count}개")
    return ", ".join(parts) or "retrieval 자료 0개"


def metadata_scope_summary(metadata_subset):
    if not isinstance(metadata_subset, dict):
        return "metadata 없음"
    return ", ".join(f"{key} {len(value) if isinstance(value, list) else 1}개" for key, value in metadata_subset.items())


def review_summary(review):
    assessment = review.get("assessment", {}) if isinstance(review, dict) else {}
    recommendations = review.get("recommendations", []) if isinstance(review, dict) else []
    fulfilled = summarize_text_items(assessment.get("fulfilled_requirements", []), limit=2)
    weak = summarize_text_items(assessment.get("missing_or_weak_requirements", []), limit=3)
    recs = summarize_text_items(recommendations, key="recommended_action", limit=2)
    lines = []
    if fulfilled:
        lines.append("충족: " + "; ".join(fulfilled))
    if weak:
        lines.append("보완: " + "; ".join(weak))
    if recs:
        lines.append("제안: " + "; ".join(recs))
    return "\n".join(lines) or "검토 결과가 도착했습니다."


def select_metadata_for_agent(metadata, keys):
    metadata = metadata if isinstance(metadata, dict) else {}
    return {key: metadata.get(key, []) for key in keys}


def select_benchmark_for_agent(benchmark, keys):
    benchmark = benchmark if isinstance(benchmark, dict) else {}
    return {key: benchmark.get(key, []) for key in keys}


def normalize_conversation_log(log):
    normalized = []
    for item in log or []:
        if not isinstance(item, dict):
            continue
        normalized.append(
            {
                "from": clean_text(item.get("from", "")),
                "to": clean_text(item.get("to", "")),
                "message": clean_text(item.get("message", "")),
            }
        )
    return [item for item in normalized if item["from"] and item["to"] and item["message"]]


def call_consult_agent_plan(metadata, preferences, ranked_jobs, retrieval_context):
    system_prompt = (
        CONSULT_AGENT_PROMPT
        + "\n\n"
        + RETRIEVAL_ONLY_PROMPT
        + "\n\n"
        "목표 직무 benchmark를 만들고, 어떤 Supporting Agent를 호출할지 보수적으로 선택해주세요. "
        "제공된 retrieval_context, retrieval_source_registry, metadata를 기준으로 삼고, Supporting Agent에는 검증된 retrieved_sources만 전달된다는 전제로 계획해주세요. "
        "Return JSON only."
    )
    user_prompt = {
        "metadata": metadata,
        "preferences": preferences,
        "ranked_job_candidates": job_context_for_feedback(ranked_jobs),
        "retrieval_context": retrieval_context,
        "retrieval_source_registry": load_retrieval_source_registry(),
        "available_supporting_agents": [
            {"key": key, "name": config["name"], "metadata_scope": config["metadata_keys"]}
            for key, config in SUPPORTING_AGENT_CONFIG.items()
        ],
        "selection_rules": [
            "관련 항목이 비어 있거나 구체성이 부족하면 호출해주세요.",
            "활동 경력이 적당히 충분해 보여도 보수적으로 보완 가능성이 있으면 호출해주세요.",
            "호출하지 않는 Agent가 있다면 conversation_log에 이유를 남겨주세요.",
        ],
        "output_schema": {
            "benchmark": {
                "target_role": "string",
                "source_count": 0,
                "benchmark_sources": [],
                "core_requirements": ["string"],
                "preferred_requirements": ["string"],
                "minimum_viable_profile": ["string"],
                "strong_profile_signals": ["string"],
                "common_rejection_risks": ["string"],
            },
            "gap_analysis": [
                {
                    "gap_name": "string",
                    "related_benchmark_requirement": "string",
                    "metadata_evidence": "string",
                    "missing_or_weak_point": "string",
                    "recommended_source_policy": "string",
                    "source_categories": ["source_category from retrieval_source_registry"],
                    "assigned_agent": "project_and_career | leadership_and_contribution | language_and_credential",
                }
            ],
            "retrieved_sources": {
                "benchmark_sources": [],
                "recommendation_sources": [],
            },
            "activated_agents": [{"agent_key": "string", "agent_name": "string", "reason": "string"}],
            "conversation_log": [{"from": "Consult Agent", "to": "Supporting Agent", "message": "string"}],
        },
    }
    result = call_openai_json(system_prompt, user_prompt, max_output_tokens=2200, timeout=22)
    activated = []
    valid_keys = set(SUPPORTING_AGENT_CONFIG)
    for item in result.get("activated_agents", []):
        key = item.get("agent_key", "")
        if key in valid_keys:
            activated.append(
                {
                    "agent_key": key,
                    "agent_name": SUPPORTING_AGENT_CONFIG[key]["name"],
                    "reason": clean_text(item.get("reason", "")),
                }
            )
    return {
        "benchmark": result.get("benchmark", {}),
        "gap_analysis": result.get("gap_analysis", []),
        "retrieved_sources": result.get("retrieved_sources", retrieval_context),
        "retrieval_source_registry": load_retrieval_source_registry(),
        "activated_agents": activated,
        "conversation_log": normalize_conversation_log(result.get("conversation_log", [])),
    }


def fallback_consult_agent_plan(metadata, preferences, ranked_jobs, retrieval_context):
    target_role = preferences.get("target_role", "") or DEFAULT_JOB_KEYWORD
    requirements = common_job_requirements(ranked_jobs)
    if not requirements:
        requirements = extract_profile_skills(metadata_to_text(metadata))[:5] or ["직무 관련 프로젝트 근거", "역할과 성과가 드러나는 CV 문장"]
    gap_analysis = [
        {
            "gap_name": "프로젝트/경험 근거 구체화",
            "related_benchmark_requirement": requirements[0] if requirements else "직무 관련 경험",
            "metadata_evidence": "metadata의 projects_and_experience, awards, skills를 확인해야 합니다.",
            "missing_or_weak_point": "역할, 산출물, 성과가 충분히 구조화되어 있는지 보수적으로 확인해야 합니다.",
            "recommended_source_policy": "상위 공고 benchmark source와 연결해 경험의 근거를 검토합니다.",
            "source_categories": ["job_posting", "internship", "competition", "external_activity"],
            "assigned_agent": "project_and_career",
        },
    ]
    activated_agents = [
        {
            "agent_key": "project_and_career",
            "agent_name": SUPPORTING_AGENT_CONFIG["project_and_career"]["name"],
            "reason": "프로젝트와 경험 항목은 목표 직무의 핵심 요구사항과 직접 연결되므로 보수적으로 검토합니다.",
        },
    ]
    return {
        "benchmark": {
            "target_role": target_role,
            "source_count": len(retrieval_context.get("benchmark_sources", [])),
            "benchmark_sources": retrieval_context.get("benchmark_sources", []),
            "core_requirements": requirements[:6],
            "preferred_requirements": [],
            "minimum_viable_profile": ["직무 관련 경험을 1개 이상 명확한 역할, 산출물, 성과 중심으로 설명해야 합니다."],
            "strong_profile_signals": ["실제 산출물, 배포, 외부 검증, 정량 성과가 있으면 강한 신호로 봅니다."],
            "common_rejection_risks": ["경험 설명이 도구 나열에 그치거나 본인 역할과 결과가 불명확하면 위험합니다."],
        },
        "gap_analysis": gap_analysis,
        "retrieved_sources": retrieval_context,
        "retrieval_source_registry": load_retrieval_source_registry(),
        "activated_agents": activated_agents,
        "conversation_log": [
            {
                "from": "Consult Agent",
                "to": "Leading Agent",
                "message": "일부 Agent 응답을 구조화하지 못해, 현재 metadata와 상위 공고 근거를 기준으로 보수적인 기본 benchmark를 구성했습니다.",
            }
        ],
    }


def call_supporting_agent(agent_key, metadata, preferences, benchmark, cv_text, retrieval_context, assigned_gap, agent_retrieval_results=None):
    config = SUPPORTING_AGENT_CONFIG[agent_key]
    agent_prompt = load_agent_prompt(config["prompt_file"])
    scoped_metadata = select_metadata_for_agent(metadata, config["metadata_keys"])
    scoped_benchmark = select_benchmark_for_agent(benchmark, config["benchmark_keys"])
    system_prompt = (
        SUPPORTING_COMMON_PROMPT
        + "\n\n"
        + RETRIEVAL_ONLY_PROMPT
        + "\n\n"
        + agent_prompt
    )
    user_prompt = {
        "instruction_from_consult_agent": config["task"],
        "target_role": preferences.get("target_role", ""),
        "preparation_period": preferences.get("preparation_period", ""),
        "additional_user_input": preferences.get("additional_user_input", ""),
        "benchmark": scoped_benchmark,
        "metadata_subset": scoped_metadata,
        "retrieved_sources": (agent_retrieval_results or {}).get("verified_sources", []),
        "retrieval_audit": {
            "raw_search_candidate_count": len((agent_retrieval_results or {}).get("raw_search_candidates", [])),
            "discarded_source_count": len((agent_retrieval_results or {}).get("discarded_sources", [])),
        },
        "assigned_gap": assigned_gap,
        "cv_text": "",
        "required_output_format": {
            "agent_name": config["name"],
            "observed_information": {},
            "assessment": {
                "fulfilled_requirements": ["string"],
                "missing_or_weak_requirements": ["string"],
                "unclear_points": ["string"],
            },
            "recommendations": [
                {
                    "gap": "string",
                    "recommended_action": "string",
                    "reason": "string",
                    "time_fit": "string",
                }
            ],
            "message_to_consult_agent": {
                "needs_review": True,
                "specific_question": "string",
            },
            "source_usage": {
                "used_source_urls": ["string"],
                "unverified_recommendations": ["string"],
            },
            "conversation_message": {
                "from": config["name"],
                "to": "Consult Agent",
                "message": "string",
            },
        },
    }
    result = call_openai_json(system_prompt, user_prompt, max_output_tokens=2200, timeout=22)
    result["agent_name"] = result.get("agent_name") or config["name"]
    return result


def fallback_supporting_review(agent_key, exc):
    config = SUPPORTING_AGENT_CONFIG[agent_key]
    return {
        "agent_name": config["name"],
        "observed_information": {},
        "assessment": {
            "fulfilled_requirements": [],
            "missing_or_weak_requirements": [
                "해당 Agent의 검토 결과를 구조화하지 못해 이 항목은 보수적으로 gap으로 유지했습니다."
            ],
            "unclear_points": [
                "Agent 검토 근거가 충분히 구조화되지 않았습니다."
            ],
        },
        "recommendations": [
            {
                "gap": "Agent 응답 형식",
                "recommended_action": "metadata 근거와 benchmark 항목을 짧고 명확한 JSON 구조로 다시 검토해야 합니다.",
                "reason": "Consult Agent가 자연어 오류 메시지가 아니라 구조화된 검토 결과를 받아야 합니다.",
                "time_fit": "즉시 수정 가능",
            }
        ],
        "message_to_consult_agent": {
            "needs_review": True,
            "specific_question": "응답 형식 복구에 실패했습니다. 해당 항목은 보수적으로 gap으로 유지해주세요.",
        },
        "conversation_message": {
            "from": config["name"],
            "to": "Consult Agent",
            "message": "검토 근거가 충분히 구조화되지 않았습니다. metadata 근거가 확인된 항목만 보수적으로 반영해주세요.",
        },
        "error": "검토 결과를 구조화하지 못했습니다.",
    }


def call_supporting_agent_revision(agent_key, metadata, preferences, benchmark, cv_text, original_review, revision_request, retrieval_context, assigned_gap, agent_retrieval_results=None):
    config = SUPPORTING_AGENT_CONFIG[agent_key]
    agent_prompt = load_agent_prompt(config["prompt_file"])
    scoped_metadata = select_metadata_for_agent(metadata, config["metadata_keys"])
    scoped_benchmark = select_benchmark_for_agent(benchmark, config["benchmark_keys"])
    system_prompt = (
        SUPPORTING_COMMON_PROMPT
        + "\n\n"
        + RETRIEVAL_ONLY_PROMPT
        + "\n\n"
        + agent_prompt
        + "\n\nConsult Agent가 1차 결과를 검토한 뒤 재검토를 요청했습니다. 기존 답변을 방어하지 말고, 요청된 기준에 맞게 더 구체적으로 수정해주세요."
    )
    user_prompt = {
        "revision_request_from_consult_agent": revision_request,
        "original_review": original_review,
        "target_role": preferences.get("target_role", ""),
        "preparation_period": preferences.get("preparation_period", ""),
        "benchmark": scoped_benchmark,
        "metadata_subset": scoped_metadata,
        "retrieved_sources": (agent_retrieval_results or {}).get("verified_sources", []),
        "retrieval_audit": {
            "raw_search_candidate_count": len((agent_retrieval_results or {}).get("raw_search_candidates", [])),
            "discarded_source_count": len((agent_retrieval_results or {}).get("discarded_sources", [])),
        },
        "assigned_gap": assigned_gap,
        "cv_text": "",
        "required_output_format": {
            "agent_name": config["name"],
            "observed_information": {},
            "assessment": {
                "fulfilled_requirements": ["string"],
                "missing_or_weak_requirements": ["string"],
                "unclear_points": ["string"],
            },
            "recommendations": [
                {
                    "gap": "string",
                    "recommended_action": "string",
                    "reason": "string",
                    "time_fit": "string",
                }
            ],
            "message_to_consult_agent": {
                "needs_review": False,
                "specific_question": "string",
            },
            "source_usage": {
                "used_source_urls": ["string"],
                "unverified_recommendations": ["string"],
            },
            "conversation_message": {
                "from": config["name"],
                "to": "Consult Agent",
                "message": "string",
            },
        },
    }
    result = call_openai_json(system_prompt, user_prompt, max_output_tokens=2200, timeout=22)
    result["agent_name"] = result.get("agent_name") or config["name"]
    result["revision_of"] = original_review.get("agent_name", config["name"]) if isinstance(original_review, dict) else config["name"]
    return result


def call_consult_agent_review(metadata, preferences, ranked_jobs, plan, supporting_reviews, retrieval_context, allow_revisions=True, prior_review=None, supporting_search_results=None):
    system_prompt = (
        CONSULT_AGENT_PROMPT
        + "\n\n"
        + RETRIEVAL_ONLY_PROMPT
        + "\n\n"
        "Supporting Agent들의 1차 결과를 검토하고 최종 통합해주세요. "
        "결과가 일반론이거나 benchmark와 약하게 연결되어 있으면 어떤 Agent에게 무엇을 다시 요청할지 정해주세요. "
        "안정 판정은 매우 엄격하게 하세요. 대화 문장은 사람이 말하듯 자연스럽고 정중하게 작성해주세요. Return JSON only."
    )
    user_prompt = {
        "metadata": metadata,
        "preferences": preferences,
        "ranked_job_candidates": job_context_for_feedback(ranked_jobs),
        "retrieval_context": retrieval_context,
        "benchmark": plan.get("benchmark", {}),
        "gap_analysis": plan.get("gap_analysis", []),
        "activated_agents": plan.get("activated_agents", []),
        "supporting_reviews": supporting_reviews,
        "supporting_retrieval_results": supporting_search_results or {},
        "prior_consult_review": prior_review or {},
        "allow_revision_requests": allow_revisions,
        "review_rules": [
            "metadata 근거 없이 추론한 내용은 최종 결과에 반영하지 마세요.",
            "retrieved source 근거 없이 외부 기회를 확정 추천하지 마세요.",
            "source URL이 없는 외부 기회는 recommendations에 넣지 마세요.",
            "마감일이 지났거나 불명확한 후보는 확정 추천하지 마세요.",
            "준비 기간 안에 실행하기 어려운 계획은 낮은 우선순위로 내리거나 제외하세요.",
            "stable은 핵심 요구사항 대부분이 구체적 근거로 충족될 때만 부여하세요.",
            "내부 오류명이나 파싱 실패 표현을 사용자 대화나 Agent 대화에 쓰지 마세요.",
            "응답 형식 문제가 있는 Agent는 '검토 근거가 부족합니다'처럼 사용자에게 이해되는 표현으로 바꿔주세요.",
            "allow_revision_requests가 true이면 필요한 재검토 요청을 revision_requests에 남겨주세요.",
            "allow_revision_requests가 false이면 추가 재검토를 요청하지 말고 최종 통합만 해주세요.",
            "각 Supporting Agent에게 검토 완료 또는 재검토 요청 메시지를 conversation_log에 남겨주세요.",
            "Supporting Agent가 사용한 verified_sources가 metadata 사실과 섞이지 않았는지 확인해주세요.",
        ],
        "output_schema": {
            "agent_reviews": {},
            "revision_requests": [{"agent_key": "string", "to": "string", "message": "string"}],
            "priority_gaps": [
                {
                    "gap": "string",
                    "evidence_from_metadata": "string",
                    "related_benchmark_requirement": "string",
                    "recommended_action_type": "string",
                    "priority": "string",
                }
            ],
            "recommendations": [
                {
                    "title": "string",
                    "type": "string",
                    "source": "string",
                    "url": "string",
                    "deadline": "string",
                    "period": "string",
                    "target_gap": "string",
                    "why_recommended": "string",
                    "expected_cv_value": "string",
                    "next_action": "string",
                    "status_note": "string",
                }
            ],
            "final_classification": {
                "status": "stable | moderate_risk | high_risk | misaligned",
                "reason": ["string"],
            },
            "recommended_focus": ["string"],
            "planner_handoff": {
                "planning_goal": "string",
                "priority_order": ["string"],
                "activities_to_plan": [
                    {
                        "target_gap": "string",
                        "action_type": "string",
                        "source_requirement": "string",
                        "schedule_sensitivity": "high | medium | low",
                        "notes_for_planner": "string",
                    }
                ],
                "constraints_to_confirm": ["string"],
                "do_not_plan": ["string"],
            },
            "handoff_to_leading_agent": "string",
            "conversation_log": [{"from": "Consult Agent", "to": "string", "message": "string"}],
        },
    }
    return call_openai_json(system_prompt, user_prompt, max_output_tokens=2200, timeout=22)


def fallback_consult_agent_review(metadata, preferences, plan, supporting_reviews, allow_revisions=False):
    priority_gaps = []
    recommended_focus = []
    for gap in plan.get("gap_analysis", [])[:6]:
        if not isinstance(gap, dict):
            continue
        priority_gaps.append(
            {
                "gap": gap.get("gap_name", "보완 항목"),
                "evidence_from_metadata": gap.get("metadata_evidence", ""),
                "related_benchmark_requirement": gap.get("related_benchmark_requirement", ""),
                "recommended_action_type": gap.get("recommended_source_policy", "metadata 근거 보강"),
                "priority": "high",
            }
        )
        if gap.get("missing_or_weak_point"):
            recommended_focus.append(gap["missing_or_weak_point"])

    if not priority_gaps:
        priority_gaps = [
            {
                "gap": "CV 근거 구체화",
                "evidence_from_metadata": "현재 metadata",
                "related_benchmark_requirement": "목표 직무 benchmark",
                "recommended_action_type": "역할, 산출물, 성과 정리",
                "priority": "medium",
            }
        ]

    revision_requests = []
    if allow_revisions:
        for agent_key, review in supporting_reviews.items():
            if review.get("error"):
                revision_requests.append(
                    {
                        "agent_key": agent_key,
                        "to": SUPPORTING_AGENT_CONFIG.get(agent_key, {}).get("name", agent_key),
                        "message": "검토 근거가 충분히 구조화되지 않았습니다. metadata, benchmark, assigned_gap 기준으로 핵심 보완점만 다시 정리해주세요.",
                    }
                )

    return {
        "agent_reviews": supporting_reviews,
        "revision_requests": revision_requests[:2],
        "priority_gaps": priority_gaps,
        "recommendations": [],
        "final_classification": {
            "status": "moderate_risk",
            "reason": [
                "일부 Agent 응답을 완전히 구조화하지 못해 안정 판정은 보수적으로 보류했습니다.",
                "현재 확인 가능한 metadata와 benchmark 기준에서는 핵심 경험의 역할, 산출물, 성과 표현을 우선 보완해야 합니다.",
            ],
        },
        "recommended_focus": recommended_focus[:5] or ["프로젝트/경험의 역할, 산출물, 성과를 구체화해주세요."],
        "planner_handoff": {
            "planning_goal": "Consult Agent가 확인한 priority gap을 실행 가능한 일정 초안과 todo로 바꿔주세요.",
            "priority_order": recommended_focus[:5],
            "activities_to_plan": [
                {
                    "target_gap": item.get("gap", ""),
                    "action_type": item.get("recommended_action_type", ""),
                    "source_requirement": "검증된 URL과 날짜가 있는 경우에만 calendar_draft에 넣어주세요.",
                    "schedule_sensitivity": "medium",
                    "notes_for_planner": item.get("evidence_from_metadata", ""),
                }
                for item in priority_gaps[:5]
            ],
            "constraints_to_confirm": ["available_time_per_week", "preferred_weekdays", "start_date"],
            "do_not_plan": ["URL 또는 일정 근거가 없는 외부 대회/시험을 확정 일정으로 만들지 마세요."],
        },
        "handoff_to_leading_agent": "구조화 가능한 근거만 사용해 사용자용 보고서로 정리해주세요.",
        "conversation_log": [
            {
                "from": "Consult Agent",
                "to": "Leading Agent",
                "message": "일부 검토 결과가 완전하지 않아, 확인 가능한 metadata와 benchmark만 사용해 보수적으로 통합했습니다.",
            }
        ],
    }


def compact_source_link(item, default_used_for="planning_reference"):
    if not isinstance(item, dict):
        return None
    url = clean_text(item.get("url", "") or item.get("source_url", ""))
    title = clean_text(item.get("title", "") or item.get("name", "") or item.get("source", ""))
    if not url and not title:
        return None
    return {
        "title": title or url,
        "url": url,
        "source_name": clean_text(item.get("source_name", "") or item.get("source", "")),
        "used_for": clean_text(item.get("used_for", "") or default_used_for),
        "deadline": clean_text(item.get("deadline", "")),
        "period": clean_text(item.get("period", "")),
        "related_gap": clean_text(item.get("related_gap", "") or item.get("target_gap", "")),
        "status_note": clean_text(item.get("status_note", "")),
    }


def collect_planner_verified_sources(retrieval_context, supporting_search_results, consult_result):
    collected = []
    seen = set()

    def add(item, default_used_for="planning_reference"):
        link = compact_source_link(item, default_used_for=default_used_for)
        if not link:
            return
        key = link.get("url") or link.get("title")
        if not key or key in seen:
            return
        seen.add(key)
        collected.append(link)

    for item in (retrieval_context or {}).get("benchmark_sources", [])[:10]:
        add(item, "benchmark")
    for item in (retrieval_context or {}).get("success_case_sources", [])[:20]:
        add(item, "success_case_reference")
    for item in (retrieval_context or {}).get("recommendation_sources", [])[:20]:
        add(item, "recommendation_reference")

    for agent_key, result in (supporting_search_results or {}).items():
        if not isinstance(result, dict):
            continue
        for item in result.get("verified_sources", [])[:8]:
            link = compact_source_link(item, default_used_for=item.get("used_for", "supporting_agent_reference"))
            if link:
                link["agent_key"] = agent_key
                add(link, link.get("used_for", "supporting_agent_reference"))

    for item in (consult_result or {}).get("recommendations", [])[:20]:
        add(item, "consult_recommendation")

    return collected[:40]


def build_planner_input(metadata, preferences, consult_result, retrieval_context, supporting_search_results):
    preferences = preferences if isinstance(preferences, dict) else {}
    user_constraints = {
        "target_role": preferences.get("target_role", ""),
        "preparation_period": preferences.get("preparation_period", ""),
        "available_time_per_week": preferences.get("available_time_per_week", ""),
        "preferred_weekdays": preferences.get("preferred_weekdays", ""),
        "preferred_location": preferences.get("preferred_location", ""),
        "online_or_offline_preference": preferences.get("online_or_offline_preference", ""),
        "budget": preferences.get("budget", ""),
        "start_date": preferences.get("start_date", ""),
    }
    return {
        "metadata_summary": {
            key: value for key, value in (metadata or {}).items()
            if key in ("education", "projects_and_experience", "awards", "leadership_and_volunteering", "languages_and_certificates", "skills")
        },
        "preferences": preferences,
        "user_constraints": user_constraints,
        "consult_result": {
            "final_classification": (consult_result or {}).get("final_classification", {}),
            "priority_gaps": (consult_result or {}).get("priority_gaps", []),
            "recommendations": (consult_result or {}).get("recommendations", []),
            "recommended_focus": (consult_result or {}).get("recommended_focus", []),
            "planner_handoff": (consult_result or {}).get("planner_handoff", {}),
        },
        "verified_sources": collect_planner_verified_sources(retrieval_context, supporting_search_results, consult_result),
        "planning_policy": {
            "calendar_is_draft_only": True,
            "calendar_write_requires_user_confirmation": True,
            "do_not_invent_dates": True,
            "confirmed_calendar_item_requires_source_url_and_date": True,
            "missing_user_constraints_must_be_listed": True,
        },
    }


def has_calendar_date(item):
    if not isinstance(item, dict):
        return False
    date_text = " ".join(
        clean_text(item.get(key, ""))
        for key in ("date", "deadline", "period")
    )
    if not date_text:
        return False
    if re.search(r"\d{4}[-./]\d{1,2}[-./]\d{1,2}|\d{1,2}[./]\d{1,2}|D-\s*\d+", date_text):
        return True
    return False


def fallback_planner_result(planner_input):
    consult = planner_input.get("consult_result", {})
    priority_gaps = consult.get("priority_gaps", [])
    recommendations = consult.get("recommendations", [])
    verified_sources = planner_input.get("verified_sources", [])
    constraints = planner_input.get("user_constraints", {})

    calendar_draft = []
    uncertain_items = []
    for source in verified_sources[:12]:
        if source.get("url") and has_calendar_date(source):
            calendar_draft.append(
                {
                    "title": source.get("title", "확인 필요 일정"),
                    "type": "other",
                    "date": "",
                    "time": "",
                    "period": source.get("period", ""),
                    "deadline": source.get("deadline", ""),
                    "source_url": source.get("url", ""),
                    "source_name": source.get("source_name", ""),
                    "related_gap": source.get("related_gap", ""),
                    "why_on_calendar": "출처와 일정 표현이 함께 확인되어 캘린더 후보로만 올렸습니다.",
                    "confirmation_required": True,
                    "confirmation_reason": "원문 페이지에서 최신 일정과 접수 상태를 사용자가 확인해야 합니다.",
                }
            )
        else:
            uncertain_items.append(
                {
                    "item": source.get("title", "외부 기회"),
                    "reason": "URL 또는 일정 정보가 충분히 확인되지 않아 확정 일정으로 넣지 않았습니다.",
                    "needed_confirmation": "원문 페이지의 모집 여부, 마감일, 진행 기간을 확인해주세요.",
                    "source_url": source.get("url", ""),
                }
            )

    todo_list = []
    for index, gap in enumerate(priority_gaps[:6], start=1):
        if not isinstance(gap, dict):
            continue
        todo_list.append(
            {
                "title": f"{index}. {gap.get('gap', '보완 항목')} 보완",
                "priority": gap.get("priority", "high") if gap.get("priority") in ("high", "medium", "low") else "high",
                "category": "other",
                "related_gap": gap.get("gap", ""),
                "evidence": gap.get("evidence_from_metadata", ""),
                "action_steps": [
                    "현재 CV에 명시된 사실만 기준으로 역할, 산출물, 성과를 정리해주세요.",
                    "필요한 외부 활동은 출처 URL과 최신 일정을 확인한 뒤 확정해주세요.",
                ],
                "estimated_effort": "사용자 가능 시간이 확인되면 재산정 필요",
                "due_basis": "준비 기간과 가능 시간이 아직 충분히 확인되지 않아 임시 우선순위로 배치했습니다.",
                "source_url": "",
                "confirmation_required": True,
            }
        )

    if not todo_list:
        todo_list.append(
            {
                "title": "우선순위 gap 재확인",
                "priority": "medium",
                "category": "retrieval_check",
                "related_gap": "Consult Agent priority gaps",
                "evidence": "Consult Agent 결과 기준",
                "action_steps": ["목표 직무, 준비 기간, 주당 가능 시간을 먼저 확인해주세요."],
                "estimated_effort": "30분",
                "due_basis": "계획 수립 전 확인 단계",
                "source_url": "",
                "confirmation_required": True,
            }
        )

    missing_constraints = [
        label for key, label in (
            ("available_time_per_week", "주당 투자 가능 시간"),
            ("preferred_weekdays", "선호 요일"),
            ("start_date", "계획 시작일"),
        )
        if not constraints.get(key)
    ]
    for label in missing_constraints:
        uncertain_items.append(
            {
                "item": label,
                "reason": "사용자 입력이 없어 주차별 계획을 확정하지 않았습니다.",
                "needed_confirmation": f"{label}을 입력해주세요.",
                "source_url": "",
            }
        )

    weekly_plan = [
        {
            "week": "Week 1",
            "goal": "핵심 gap과 외부 일정 확인",
            "tasks": [
                "Consult Agent가 표시한 priority gap을 사용자와 확인합니다.",
                "외부 대회/시험/채용 URL의 최신 모집 여부와 마감일을 확인합니다.",
            ],
            "expected_output": "확정 가능한 calendar item 목록과 보류 항목 목록",
            "confirmation_required": True,
        },
        {
            "week": "Week 2",
            "goal": "CV 근거 보강 초안 작성",
            "tasks": [
                "프로젝트/경험별 역할, 산출물, 성과 문장을 보강합니다.",
                "필요한 시험·대회·활동은 확인된 일정만 기준으로 준비 단계를 쪼갭니다.",
            ],
            "expected_output": "수정된 CV bullet 초안과 지원 준비 todo",
            "confirmation_required": True,
        },
    ]

    return {
        "planner_summary": "검증된 출처와 사용자 제약이 부족한 항목은 확정 일정으로 넣지 않고 확인 필요로 분리했습니다.",
        "calendar_draft": calendar_draft[:10],
        "todo_list": todo_list,
        "weekly_plan": weekly_plan,
        "source_links": [
            {
                "title": source.get("title", ""),
                "url": source.get("url", ""),
                "source_name": source.get("source_name", ""),
                "used_for": source.get("used_for", ""),
            }
            for source in verified_sources[:20]
            if source.get("url")
        ],
        "confirmation_questions": [f"{label}을 알려주시면 일정을 더 정확히 쪼갤 수 있습니다." for label in missing_constraints],
        "uncertain_items": uncertain_items[:20],
        "calendar_write_request": {
            "requires_user_confirmation": True,
            "message": "아직 Google Calendar에는 아무 것도 쓰지 않았습니다. 사용자가 확인한 뒤에만 캘린더 등록 단계로 넘어갑니다.",
        },
        "conversation_message": {
            "from": "Planner Agent",
            "to": "Leading Agent",
            "message": f"확정 가능한 캘린더 후보 {len(calendar_draft[:10])}개, Todo {len(todo_list)}개, 확인 필요 항목 {len(uncertain_items[:20])}개로 계획 초안을 정리했습니다.",
        },
    }


def normalize_planner_result(result):
    if not isinstance(result, dict):
        return fallback_planner_result({"consult_result": {}, "verified_sources": [], "user_constraints": {}})
    if isinstance(result.get("planner_result"), dict):
        result = result["planner_result"]

    if result.get("planning_summary") and not result.get("planner_summary"):
        result["planner_summary"] = result.get("planning_summary")

    normalized_calendar = []
    for item in result.get("calendar_draft", []) or []:
        if not isinstance(item, dict):
            continue
        normalized_calendar.append(
            {
                "title": item.get("title", ""),
                "type": item.get("type", ""),
                "date": item.get("date", ""),
                "time": item.get("time", "") or " ".join(value for value in [item.get("start_time", ""), item.get("end_time", "")] if value),
                "period": item.get("period", ""),
                "deadline": item.get("deadline", ""),
                "source_url": item.get("source_url", "") or item.get("url", ""),
                "source_name": item.get("source_name", "") or item.get("source", ""),
                "related_gap": item.get("related_gap", ""),
                "why_on_calendar": item.get("why_on_calendar", "") or item.get("reason", ""),
                "confirmation_required": bool(item.get("confirmation_required", True)),
                "confirmation_reason": item.get("confirmation_reason", "") or ("사용자 확인 후 캘린더 반영이 필요합니다." if item.get("confirmation_required", True) else ""),
            }
        )
    result["calendar_draft"] = normalized_calendar

    normalized_todos = []
    for item in result.get("todo_list", []) or []:
        if not isinstance(item, dict):
            continue
        normalized_todos.append(
            {
                "title": item.get("title", "") or item.get("task", ""),
                "priority": item.get("priority", "medium"),
                "category": item.get("category", "other"),
                "related_gap": item.get("related_gap", ""),
                "evidence": item.get("evidence", ""),
                "action_steps": item.get("action_steps", []) or ([item.get("task", "")] if item.get("task") else []),
                "estimated_effort": item.get("estimated_effort", "") or item.get("estimated_time", ""),
                "due_basis": item.get("due_basis", "") or item.get("deadline", ""),
                "source_url": item.get("source_url", "") or item.get("url", ""),
                "confirmation_required": bool(item.get("confirmation_required", True)),
                "status": item.get("status", "not_started"),
            }
        )
    result["todo_list"] = normalized_todos

    normalized_weekly = []
    for item in result.get("weekly_plan", []) or []:
        if not isinstance(item, dict):
            continue
        normalized_weekly.append(
            {
                "week": str(item.get("week", "")),
                "goal": item.get("goal", "") or item.get("focus", ""),
                "tasks": item.get("tasks", []),
                "expected_output": item.get("expected_output", ""),
                "confirmation_required": bool(item.get("confirmation_required", True)),
            }
        )
    result["weekly_plan"] = normalized_weekly

    normalized_uncertain = []
    for item in result.get("uncertain_items", []) or []:
        if not isinstance(item, dict):
            continue
        normalized_uncertain.append(
            {
                "item": item.get("item", ""),
                "reason": item.get("reason", ""),
                "needed_confirmation": item.get("needed_confirmation", "") or item.get("needed_user_input", ""),
                "source_url": item.get("source_url", "") or item.get("url", ""),
            }
        )
    result["uncertain_items"] = normalized_uncertain

    calendar_write = result.get("calendar_write_request") if isinstance(result.get("calendar_write_request"), dict) else {}
    calendar_write["requires_user_confirmation"] = True
    calendar_write["message"] = calendar_write.get("message") or "위 일정 초안을 Google Calendar에 추가할지 사용자 확인이 필요합니다."
    result["calendar_write_request"] = calendar_write
    result.setdefault("source_links", [])
    result.setdefault("confirmation_questions", [])
    return result


def call_planner_agent(planner_input):
    user_prompt = {
        "planner_input": planner_input,
        "instruction": (
            "Consult Agent가 승인한 gap과 verified_sources만 사용해 calendar_draft, todo_list, weekly_plan을 작성해주세요. "
            "일정과 URL이 명확하지 않은 외부 기회는 uncertain_items로 보내고, Google Calendar write는 절대 하지 마세요."
        ),
    }
    return call_openai_json(PLANNER_AGENT_PROMPT, user_prompt, max_output_tokens=2200, timeout=22)


def call_leading_agent_final(metadata, preferences, consult_result, planner_result=None):
    system_prompt = (
        LEADING_AGENT_PROMPT
        + "\n\n"
        "직접 세부 항목을 재평가하지 말고 Consult Agent의 결과를 받아 "
        "사용자에게 보여줄 최종 보고서로 통합해주세요. 준비 기간 안에서 실행하기 어려운 계획은 최종안에 넣지 마세요. "
        "안정/위험 분류를 느슨하게 하지 마세요. 문장은 사람이 말하듯 자연스럽고 정중하게 작성해주세요. Return JSON only."
    )
    user_prompt = {
        "metadata": metadata,
        "preferences": preferences,
        "consult_result": consult_result,
        "planner_result": planner_result or {},
        "output_schema": {
            "final_report": {
                "target_role": "string",
                "preparation_period": "string",
                "overall_status": "string",
                "summary": "string",
                "key_strengths": ["string"],
                "critical_gaps": ["string"],
                "agent_feedback_summary": {},
                "recommended_strategy": ["string"],
                "next_actions": ["string"],
                "calendar_draft_summary": "string",
                "todo_summary": "string",
                "source_links": [{"title": "string", "url": "string", "used_for": "string"}],
                "cautions": ["string"],
            },
            "conversation_log": [{"from": "Leading Agent", "to": "Consult Agent", "message": "string"}],
        },
    }
    return call_openai_json(system_prompt, user_prompt, max_output_tokens=1800, timeout=20)


def fallback_leading_agent_final(preferences, consult_result, planner_result=None):
    classification = consult_result.get("final_classification", {})
    planner_result = planner_result or {}
    return {
        "final_report": {
            "target_role": preferences.get("target_role", "") or "목표 직무",
            "preparation_period": preferences.get("preparation_period", ""),
            "overall_status": classification.get("status", "moderate_risk"),
            "summary": "Agent 일부 응답이 완전히 구조화되지 않아, 확인 가능한 metadata와 benchmark만 기준으로 보수적인 피드백을 정리했습니다.",
            "key_strengths": [],
            "critical_gaps": summarize_text_items(consult_result.get("priority_gaps", []), key="gap", limit=5),
            "agent_feedback_summary": {},
            "recommended_strategy": consult_result.get("recommended_focus", [])[:5],
            "next_actions": [
                "대표 프로젝트 1개를 역할, 산출물, 성과 중심으로 다시 정리해주세요.",
                "목표 직무 benchmark의 핵심 요구사항과 연결되는 근거만 CV 앞쪽에 배치해주세요.",
            ],
            "calendar_draft_summary": f"캘린더 초안 {len(planner_result.get('calendar_draft', []))}개가 준비되었습니다. 아직 실제 캘린더에는 등록하지 않았습니다.",
            "todo_summary": f"Todo {len(planner_result.get('todo_list', []))}개가 준비되었습니다.",
            "source_links": planner_result.get("source_links", [])[:10],
            "cautions": [
                "외부 대회, 시험, 채용 일정은 원문 URL에서 최신 마감일을 확인한 뒤 확정해야 합니다.",
                "Google Calendar 등록은 사용자 확인 이후에만 진행해야 합니다.",
            ],
        },
        "conversation_log": [
            {
                "from": "Leading Agent",
                "to": "Consult Agent",
                "message": "확인 가능한 근거만 사용해 사용자용 최종 보고서로 정리했습니다.",
            }
        ],
    }


def with_lane(message, agent_key=None):
    cloned = dict(message or {})
    if agent_key:
        cloned["lane"] = agent_key
        cloned["agent_key"] = agent_key
    return cloned


def normalize_lane_result(agent_key, lane_messages, support_review, clone_review):
    return {
        "agent_key": agent_key,
        "agent_name": SUPPORTING_AGENT_CONFIG.get(agent_key, {}).get("name", agent_key),
        "messages": [with_lane(message, agent_key) for message in normalize_conversation_log(lane_messages)],
        "support_review": support_review,
        "consult_clone_review": clone_review,
        "status": (
            "approved"
            if not (clone_review or {}).get("revision_requests")
            else "reviewed_with_remaining_requests"
        ),
    }


def process_supporting_consult_lane(item, metadata, preferences, ranked_jobs, plan, cv_text, retrieval_context, supporting_search_result, emit_event=None):
    agent_key = item["agent_key"]
    agent_name = item.get("agent_name") or SUPPORTING_AGENT_CONFIG.get(agent_key, {}).get("name", agent_key)
    consult_clone_name = f"Consult Agent Clone · {agent_name}"
    scoped_metadata = select_metadata_for_agent(metadata, SUPPORTING_AGENT_CONFIG[agent_key]["metadata_keys"])
    scoped_gaps = assigned_gaps_for_agent(agent_key, plan.get("gap_analysis", []))
    scoped_plan = {
        **plan,
        "activated_agents": [item],
        "gap_analysis": scoped_gaps,
    }
    scoped_search_results = {agent_key: supporting_search_result}
    lane_messages = []

    def add_lane_message(message):
        normalized = normalize_conversation_log([message])
        if not normalized:
            return
        lane_message = with_lane(normalized[0], agent_key)
        lane_messages.append(lane_message)
        if emit_event:
            emit_event("conversation", lane_message)

    add_lane_message(
        {
            "from": consult_clone_name,
            "to": agent_name,
            "message": (
                "이 lane에서는 제가 해당 Supporting Agent만 전담해서 검토하겠습니다.\n"
                f"- 호출 이유: {item.get('reason', '')}\n"
                f"- metadata scope: {metadata_scope_summary(scoped_metadata)}\n"
                f"- assigned_gap: {', '.join(summarize_text_items(scoped_gaps, key='gap_name', limit=4)) or '없음'}\n"
                f"- verified_sources: {len((supporting_search_result or {}).get('verified_sources', []))}개"
            ),
        }
    )

    try:
        support_review = call_supporting_agent(
            agent_key,
            metadata,
            preferences,
            plan["benchmark"],
            cv_text,
            retrieval_context,
            scoped_gaps,
            supporting_search_result,
        )
    except Exception as exc:
        support_review = fallback_supporting_review(agent_key, exc)

    add_lane_message(
        {
            "from": agent_name,
            "to": consult_clone_name,
            "message": "1차 검토 결과를 전달드립니다.\n" + review_summary(support_review),
        }
    )
    support_message = support_review.get("conversation_message") if isinstance(support_review, dict) else None
    if isinstance(support_message, dict):
        support_message = dict(support_message)
        if support_message.get("to") == "Consult Agent":
            support_message["to"] = consult_clone_name
        add_lane_message(support_message)

    if FAST_AGENT_MODE:
        first_clone_review = fallback_consult_agent_review(metadata, preferences, scoped_plan, {agent_key: support_review}, allow_revisions=False)
    else:
        try:
            first_clone_review = call_consult_agent_review(
                metadata,
                preferences,
                ranked_jobs,
                scoped_plan,
                {agent_key: support_review},
                retrieval_context,
                allow_revisions=True,
                supporting_search_results=scoped_search_results,
            )
        except Exception:
            first_clone_review = fallback_consult_agent_review(metadata, preferences, scoped_plan, {agent_key: support_review}, allow_revisions=True)

    for message in normalize_conversation_log(first_clone_review.get("conversation_log", [])):
        if message.get("from") == "Consult Agent":
            message["from"] = consult_clone_name
        if message.get("to") == "Consult Agent":
            message["to"] = consult_clone_name
        add_lane_message(message)

    revision_requests = [] if FAST_AGENT_MODE else [
        request for request in first_clone_review.get("revision_requests", [])
        if isinstance(request, dict) and request.get("agent_key") == agent_key
    ][:1]
    if revision_requests:
        request = revision_requests[0]
        add_lane_message(
            {
                "from": consult_clone_name,
                "to": agent_name,
                "message": (
                    clean_text(request.get("message", "결과를 더 구체적으로 재검토해주세요."))
                    + "\n"
                    + f"- 재검토 assigned_gap: {', '.join(summarize_text_items(scoped_gaps, key='gap_name', limit=4)) or '없음'}"
                ),
            }
        )
        try:
            revised_review = call_supporting_agent_revision(
                agent_key,
                metadata,
                preferences,
                plan["benchmark"],
                cv_text,
                support_review,
                request,
                retrieval_context,
                scoped_gaps,
                supporting_search_result,
            )
            support_review = revised_review
            add_lane_message(
                {
                    "from": agent_name,
                    "to": consult_clone_name,
                    "message": "재검토 결과를 전달드립니다.\n" + review_summary(revised_review),
                }
            )
        except Exception as exc:
            revised_review = fallback_supporting_review(agent_key, exc)
            revised_review["revision_note"] = "재검토 결과를 구조화하지 못해 보수적으로 gap으로 유지했습니다."
            support_review = revised_review
            add_lane_message(
                {
                    "from": agent_name,
                    "to": consult_clone_name,
                    "message": "재검토 중 문제가 있어 확인 가능한 내용만 보수적으로 다시 전달드립니다.\n" + review_summary(revised_review),
                }
            )

    if FAST_AGENT_MODE:
        clone_final_review = fallback_consult_agent_review(metadata, preferences, scoped_plan, {agent_key: support_review}, allow_revisions=False)
    else:
        try:
            clone_final_review = call_consult_agent_review(
                metadata,
                preferences,
                ranked_jobs,
                scoped_plan,
                {agent_key: support_review},
                retrieval_context,
                allow_revisions=False,
                prior_review=first_clone_review,
                supporting_search_results=scoped_search_results,
            )
        except Exception:
            clone_final_review = fallback_consult_agent_review(metadata, preferences, scoped_plan, {agent_key: support_review}, allow_revisions=False)

    for message in normalize_conversation_log(clone_final_review.get("conversation_log", [])):
        if message.get("from") == "Consult Agent":
            message["from"] = consult_clone_name
        if message.get("to") == "Consult Agent":
            message["to"] = consult_clone_name
        add_lane_message(message)
    add_lane_message(
        {
            "from": consult_clone_name,
            "to": "Final Consult Agent",
            "message": (
                "이 lane의 검토를 마쳤습니다.\n"
                f"- priority gaps: {', '.join(summarize_text_items(clone_final_review.get('priority_gaps', []), key='gap', limit=3)) or '없음'}\n"
                f"- recommendations: {', '.join(summarize_text_items(clone_final_review.get('recommendations', []), key='title', limit=2)) or '없음'}"
            ),
        }
    )
    lane_result = normalize_lane_result(agent_key, lane_messages, support_review, clone_final_review)
    lane_result["_emitted_live"] = bool(emit_event)
    return agent_key, support_review, clone_final_review, lane_result


def build_feedback_loop(cv_text, metadata, preferences, ranked_jobs, emit=None):
    if not OPENAI_API_KEY:
        return {"error": "OPENAI_API_KEY가 없어 Feedback Loop를 실행하지 못했습니다."}

    emit_lock = Lock()

    def emit_event(event, payload):
        if emit:
            with emit_lock:
                emit(event, payload)

    conversation_log = [
        {
            "from": "Leading Agent",
            "to": "Consult Agent",
            "message": "사용자의 metadata와 선호 정보를 전달드립니다. 목표 직무 기준으로 benchmark를 만들고, 필요한 Supporting Agent를 보수적으로 선택해주세요.",
        }
    ]
    emit_event("conversation", conversation_log[-1])
    emit_event("status", {"message": "Consult Agent가 benchmark와 호출할 Supporting Agent를 정하고 있습니다."})
    retrieval_context = build_retrieval_context(ranked_jobs, preferences.get("target_role", ""))
    retrieval_message = {
        "from": "Consult Agent",
        "to": "Retrieval Context",
        "message": (
            "공개 공고 후보를 benchmark source 형식으로 정리했습니다.\n"
            f"- 기준 직무: {preferences.get('target_role', '') or '미지정'}\n"
            f"- benchmark_sources: {len(retrieval_context.get('benchmark_sources', []))}개\n"
            f"- success_case_sources: {len(retrieval_context.get('success_case_sources', []))}개\n"
            f"- debug 저장: {retrieval_context.get('debug_success_cases_path', '없음')}\n"
            f"- 상위 source: {', '.join(summarize_text_items(retrieval_context.get('benchmark_sources', []), key='title', limit=3)) or '없음'}"
        ),
    }
    conversation_log.append(retrieval_message)
    emit_event("conversation", retrieval_message)
    try:
        plan = call_consult_agent_plan(metadata, preferences, ranked_jobs, retrieval_context)
    except Exception:
        plan = fallback_consult_agent_plan(metadata, preferences, ranked_jobs, retrieval_context)
    retrieval_context = plan.get("retrieved_sources") or retrieval_context
    benchmark = plan.get("benchmark", {})
    gap_analysis = plan.get("gap_analysis", [])
    plan_message = {
        "from": "Consult Agent",
        "to": "Leading Agent",
        "message": (
            "benchmark와 gap 분석을 만들었습니다.\n"
            f"- core requirements: {', '.join(summarize_text_items(benchmark.get('core_requirements', []), limit=4)) or '없음'}\n"
            f"- minimum profile: {', '.join(summarize_text_items(benchmark.get('minimum_viable_profile', []), limit=3)) or '없음'}\n"
            f"- gap: {', '.join(summarize_text_items(gap_analysis, key='gap_name', limit=5)) or '없음'}\n"
            f"- retrieved sources: {retrieval_counts(retrieval_context)}"
        ),
    }
    conversation_log.append(plan_message)
    emit_event("conversation", plan_message)
    conversation_log.extend(plan.get("conversation_log", []))
    for message in plan.get("conversation_log", []):
        emit_event("conversation", message)
    emit_event(
        "agents_selected",
        {
            "activatedAgents": plan.get("activated_agents", []),
            "benchmark": plan.get("benchmark", {}),
            "gapAnalysis": plan.get("gap_analysis", []),
            "retrievedSources": retrieval_context,
        },
    )

    supporting_reviews = {}
    consult_clone_reviews = {}
    lane_conversations = {}
    supporting_search_results = {}
    active_items = plan.get("activated_agents", [])
    emit_event("status", {"message": "선택된 Supporting Agent와 Consult Clone들이 lane별 병렬 검토를 시작했습니다."})

    for item in active_items:
        scoped_gaps = assigned_gaps_for_agent(item["agent_key"], plan.get("gap_analysis", []))
        retrieval_results = build_supporting_search_results(item["agent_key"], preferences, scoped_gaps)
        supporting_search_results[item["agent_key"]] = retrieval_results
        emit_event(
            "lane_started",
            {
                "agentKey": item["agent_key"],
                "agentName": item.get("agent_name", SUPPORTING_AGENT_CONFIG.get(item["agent_key"], {}).get("name", item["agent_key"])),
                "consultCloneName": f"Consult Agent Clone · {item.get('agent_name', item['agent_key'])}",
                "verifiedSourceCount": len(retrieval_results.get("verified_sources", [])),
                "discardedSourceCount": len(retrieval_results.get("discarded_sources", [])),
            },
        )

    write_debug_json(
        "supporting_agent_retrieval_audit.json",
        {
            "target_role": preferences.get("target_role", ""),
            "retrieved_at": time.strftime("%Y-%m-%d"),
            "results_by_agent": supporting_search_results,
        },
    )

    with ThreadPoolExecutor(max_workers=min(4, max(1, len(active_items)))) as executor:
        futures = {
            executor.submit(
                process_supporting_consult_lane,
                item,
                metadata,
                preferences,
                ranked_jobs,
                plan,
                cv_text,
                retrieval_context,
                supporting_search_results.get(item["agent_key"], {}),
                emit_event,
            ): item
            for item in active_items
        }
        for future in as_completed(futures):
            item = futures[future]
            agent_key = item["agent_key"]
            try:
                lane_agent_key, support_review, clone_review, lane_result = future.result()
                agent_key = lane_agent_key
            except Exception as exc:
                support_review = fallback_supporting_review(agent_key, exc)
                scoped_plan = {**plan, "activated_agents": [item], "gap_analysis": assigned_gaps_for_agent(agent_key, plan.get("gap_analysis", []))}
                clone_review = fallback_consult_agent_review(metadata, preferences, scoped_plan, {agent_key: support_review}, allow_revisions=False)
                lane_result = normalize_lane_result(
                    agent_key,
                    [
                        {
                            "from": item.get("agent_name", SUPPORTING_AGENT_CONFIG.get(agent_key, {}).get("name", agent_key)),
                            "to": f"Consult Agent Clone · {item.get('agent_name', agent_key)}",
                            "message": "lane 처리 중 문제가 있어 확인 가능한 내용만 보수적으로 전달했습니다.\n" + review_summary(support_review),
                        }
                    ],
                    support_review,
                    clone_review,
                )

            supporting_reviews[agent_key] = support_review
            consult_clone_reviews[agent_key] = clone_review
            lane_conversations[agent_key] = lane_result
            for message in lane_result.get("messages", []):
                conversation_log.append(message)
                if not lane_result.get("_emitted_live"):
                    emit_event("conversation", message)
            emit_event("supporting_review", {"agentKey": agent_key, "review": support_review})
            emit_event("consult_clone_review", {"agentKey": agent_key, "review": clone_review, "lane": lane_result})
            emit_event(
                "status",
                {
                    "message": f"{lane_result.get('agent_name', agent_key)} lane의 Consult Clone 검토가 완료되었습니다."
                },
            )

    emit_event("status", {"message": "Final Consult Agent가 각 Consult Clone의 결과를 모아 최종 통합하고 있습니다."})
    first_consult_review = {
        "agent_reviews": supporting_reviews,
        "consult_clone_reviews": consult_clone_reviews,
        "lane_summary": {
            key: {
                "status": value.get("status"),
                "agent_name": value.get("agent_name"),
                "message_count": len(value.get("messages", [])),
            }
            for key, value in lane_conversations.items()
        },
        "revision_requests": [],
        "conversation_log": [
            {
                "from": "Consult Agent Clones",
                "to": "Final Consult Agent",
                "message": (
                    "각 lane의 1:1 검토 결과를 전달합니다.\n"
                    f"- 완료 lane: {', '.join(SUPPORTING_AGENT_CONFIG.get(key, {}).get('name', key) for key in lane_conversations)}\n"
                    + ("Fast Mode에서는 별도 Final Consult LLM 호출 없이 Supporting Agent 결과를 바로 통합합니다." if FAST_AGENT_MODE else "Final Consult Agent는 clone 결과를 합쳐 전체 우선순위와 최종 위험 분류만 정리해주세요.")
                ),
            }
        ],
    }
    conversation_log.extend(normalize_conversation_log(first_consult_review.get("conversation_log", [])))
    for message in normalize_conversation_log(first_consult_review.get("conversation_log", [])):
        emit_event("conversation", message)

    if FAST_AGENT_MODE:
        emit_event("status", {"message": "Fast Mode가 Supporting Agent 결과를 바로 통합하고 있습니다."})
        consult_review = fallback_consult_agent_review(metadata, preferences, plan, supporting_reviews, allow_revisions=False)
    else:
        emit_event("status", {"message": "Consult Agent가 최종 통합 결과를 정리하고 있습니다."})
        try:
            consult_review = call_consult_agent_review(
                metadata,
                preferences,
                ranked_jobs,
                plan,
                supporting_reviews,
                retrieval_context,
                allow_revisions=False,
                prior_review=first_consult_review,
                supporting_search_results=supporting_search_results,
            )
        except Exception:
            consult_review = fallback_consult_agent_review(metadata, preferences, plan, supporting_reviews, allow_revisions=False)
    conversation_log.extend(normalize_conversation_log(consult_review.get("conversation_log", [])))
    for message in normalize_conversation_log(consult_review.get("conversation_log", [])):
        emit_event("conversation", message)
    emit_event("consult_result", consult_review)

    planner_input = build_planner_input(metadata, preferences, consult_review, retrieval_context, supporting_search_results)
    planner_handoff_message = {
        "from": "Leading Agent",
        "to": "Planner Agent",
        "message": (
            "Consult Agent의 최종 검토 결과를 일정과 todo 초안으로 바꿔주세요.\n"
            f"- final status: {consult_review.get('final_classification', {}).get('status', '미분류')}\n"
            f"- priority gaps: {', '.join(summarize_text_items(consult_review.get('priority_gaps', []), key='gap', limit=4)) or '없음'}\n"
            f"- verified source links: {len(planner_input.get('verified_sources', []))}개\n"
            "- URL과 날짜 근거가 함께 있는 항목만 캘린더 후보로 올리고, 나머지는 확인 필요로 분리해주세요."
        ),
    }
    conversation_log.append(planner_handoff_message)
    emit_event("conversation", planner_handoff_message)
    emit_event("status", {"message": "Planner Agent가 검증된 source를 기준으로 Calendar Draft와 Todo를 만들고 있습니다."})
    if FAST_AGENT_MODE:
        planner_result = fallback_planner_result(planner_input)
    else:
        try:
            planner_result = call_planner_agent(planner_input)
        except Exception:
            planner_result = fallback_planner_result(planner_input)
    planner_result = normalize_planner_result(planner_result)
    planner_message = planner_result.get("conversation_message") if isinstance(planner_result, dict) else None
    if isinstance(planner_message, dict):
        normalized_messages = normalize_conversation_log([planner_message])
        conversation_log.extend(normalized_messages)
        for message in normalized_messages:
            emit_event("conversation", message)
    else:
        fallback_planner_message = {
            "from": "Planner Agent",
            "to": "Leading Agent",
            "message": (
                f"Calendar Draft {len(planner_result.get('calendar_draft', []))}개, "
                f"Todo {len(planner_result.get('todo_list', []))}개, "
                f"확인 필요 항목 {len(planner_result.get('uncertain_items', []))}개로 계획 초안을 만들었습니다."
            ),
        }
        conversation_log.append(fallback_planner_message)
        emit_event("conversation", fallback_planner_message)
    emit_event("planner_result", planner_result)

    emit_event("status", {"message": "Leading Agent가 사용자용 최종 보고서로 정리하고 있습니다."})
    final_handoff_message = {
        "from": "Consult Agent",
        "to": "Leading Agent",
        "message": (
            "최종 통합 결과를 전달합니다.\n"
            f"- final status: {consult_review.get('final_classification', {}).get('status', '미분류')}\n"
            f"- priority gaps: {', '.join(summarize_text_items(consult_review.get('priority_gaps', []), key='gap', limit=4)) or '없음'}\n"
            f"- recommendations: {', '.join(summarize_text_items(consult_review.get('recommendations', []), key='title', limit=3)) or '없음'}\n"
            f"- planner draft: calendar {len(planner_result.get('calendar_draft', []))}개 / todo {len(planner_result.get('todo_list', []))}개"
        ),
    }
    conversation_log.append(final_handoff_message)
    emit_event("conversation", final_handoff_message)
    if FAST_AGENT_MODE:
        leading_final = fallback_leading_agent_final(preferences, consult_review, planner_result)
    else:
        try:
            leading_final = call_leading_agent_final(metadata, preferences, consult_review, planner_result)
        except Exception:
            leading_final = fallback_leading_agent_final(preferences, consult_review, planner_result)
    conversation_log.extend(normalize_conversation_log(leading_final.get("conversation_log", [])))
    for message in normalize_conversation_log(leading_final.get("conversation_log", [])):
        emit_event("conversation", message)

    return {
        "mode": "fast_parallel_consult_clones" if FAST_AGENT_MODE else "multi_call_parallel_consult_clones",
        "retrievalPolicy": "consulting_source_registry_quality_gate",
        "retrievedSources": retrieval_context,
        "supportingRetrievalResults": supporting_search_results,
        "benchmark": plan.get("benchmark", {}),
        "gapAnalysis": plan.get("gap_analysis", []),
        "activatedAgents": plan.get("activated_agents", []),
        "supportingReviews": supporting_reviews,
        "consultCloneReviews": consult_clone_reviews,
        "laneConversations": lane_conversations,
        "firstConsultReview": first_consult_review,
        "consultResult": consult_review,
        "plannerInput": {
            "user_constraints": planner_input.get("user_constraints", {}),
            "verified_source_count": len(planner_input.get("verified_sources", [])),
            "planning_policy": planner_input.get("planning_policy", {}),
        },
        "plannerResult": planner_result,
        "leadingReport": leading_final.get("final_report", {}),
        "conversationLog": conversation_log,
    }


def safe_feedback_loop(cv_text, metadata, preferences, ranked_jobs):
    try:
        return build_feedback_loop(cv_text, metadata, preferences, ranked_jobs)
    except Exception as exc:
        return {"error": "Feedback Loop를 완료하지 못했습니다. metadata를 확인한 뒤 다시 실행해주세요."}



def ensure_bullet_text(value):
    if isinstance(value, list):
        items = [clean_text(str(item)) for item in value if clean_text(str(item))]
        return "\n".join(f"- {item.lstrip('-• ').strip()}" for item in items)

    value = clean_text(str(value or ""))
    if not value:
        return ""
    lines = [line.strip() for line in re.split(r"\n+|(?<=다\.)\s+|(?<=함\.)\s+", value) if line.strip()]
    return "\n".join(f"- {line.lstrip('-• ').strip()}" for line in lines)


def load_metadata_contract():
    with open(ROOT / "metadata_schema.json", "r", encoding="utf-8") as schema_file:
        return json.load(schema_file)


METADATA_CONTRACT = load_metadata_contract()
METADATA_SCHEMA = {
    category: list(config.get("fields", {}).keys())
    for category, config in METADATA_CONTRACT["categories"].items()
}
SUBJECTIVE_METADATA_PATTERNS = [
    "확인 필요",
    "확인이 필요",
    "구체적인 URL",
    "기재되어 있으나",
    "명시되어 있으나",
    "추정",
    "보완 필요",
    "보완이 필요",
    "확실하지 않",
    "불명",
]


def clean_metadata_item(category, item):
    if not isinstance(item, dict):
        raw_text = clean_text(str(item or ""))
        return {field: raw_text if field in ("raw_text", "content", "description") else "" for field in METADATA_SCHEMA[category]}
    return {field: clean_text(item.get(field, "")) for field in METADATA_SCHEMA[category]}


def contains_subjective_metadata(value):
    return any(pattern in value for pattern in SUBJECTIVE_METADATA_PATTERNS)


def has_explicit_url(value):
    return bool(re.search(r"https?://|www\.|github\.com/|linkedin\.com/", value, re.IGNORECASE))


def remove_subjective_metadata_items(category, items):
    filtered = []
    for item in items:
        item_text = " ".join(value for value in item.values() if value)
        if contains_subjective_metadata(item_text):
            continue
        if re.search(r"github|linked\s*in|linkedin|portfolio", item_text, re.IGNORECASE) and not has_explicit_url(item_text):
            continue
        filtered.append(item)
    return filtered


def infer_education_fields(item):
    raw_text = item.get("raw_text", "")
    source_text = " ".join(value for value in [raw_text, item.get("school", ""), item.get("degree", ""), item.get("major", ""), item.get("period", "")] if value)

    if not item.get("school"):
        school_match = re.search(r"([가-힣A-Za-z\s]+?(?:대학교|대학|University))", source_text)
        if school_match:
            item["school"] = clean_text(school_match.group(1))

    if not item.get("degree"):
        if re.search(r"학사|Bachelor|B\.S\.|B\.A\.", source_text, re.IGNORECASE):
            item["degree"] = "학사"
        elif re.search(r"석사|Master|M\.S\.|M\.A\.", source_text, re.IGNORECASE):
            item["degree"] = "석사"
        elif re.search(r"박사|Ph\.?D|Doctor", source_text, re.IGNORECASE):
            item["degree"] = "박사"

    if not item.get("major"):
        major_match = re.search(r"(?:대학교|대학|University)\s*([가-힣A-Za-z\s]+?)(?:학사|석사|박사|Bachelor|Master|Ph\.?D|과정|전공)", source_text, re.IGNORECASE)
        if major_match:
            item["major"] = re.sub(r"\s+", " ", clean_text(major_match.group(1)))

    if not item.get("period"):
        period_match = re.search(
            r"(\d{4}\s*년\s*\d{1,2}\s*월)\s*(?:부터|~|-|–|—|to)\s*(\d{4}\s*년\s*\d{1,2}\s*월|현재|present)",
            source_text,
            re.IGNORECASE,
        )
        if period_match:
            item["period"] = f"{clean_text(period_match.group(1))} - {clean_text(period_match.group(2))}"

    return item


def normalize_metadata(metadata):
    normalized = {}
    metadata = metadata if isinstance(metadata, dict) else {}
    for category, fields in METADATA_SCHEMA.items():
        items = metadata.get(category, [])
        if isinstance(items, dict):
            items = [items]
        if not isinstance(items, list):
            items = []
        cleaned_items = [clean_metadata_item(category, item) for item in items]
        if category == "education":
            cleaned_items = [infer_education_fields(item) for item in cleaned_items]
        cleaned_items = remove_subjective_metadata_items(category, cleaned_items)
        normalized[category] = [item for item in cleaned_items if any(item.get(field) for field in fields)]
    return normalized


def metadata_to_text(metadata):
    lines = []
    for category, items in metadata.items():
        for item in items:
            values = [value for key, value in item.items() if key != "raw_text" and value]
            if not values and item.get("raw_text"):
                values = [item["raw_text"]]
            if values:
                lines.append(f"{category}: " + " / ".join(values))
    return "\n".join(lines)


def call_openai_pdf_field_mapping(pdf_bytes, filename, target_role=""):
    if not OPENAI_API_KEY:
        raise ValueError("OPENAI_API_KEY가 필요합니다. LLM으로 PDF를 읽으려면 서버 실행 시 API 키를 설정해주세요.")

    encoded_pdf = base64.b64encode(pdf_bytes).decode("ascii")
    system_prompt = (
        "You are HICAREER, a CV metadata extraction agent. "
        "Read the attached PDF and fill the exact metadata JSON contract used by the app. "
        "This is data entry into a schema, not summarization, advice, or interpretation. "
        "Return JSON only."
    )
    user_prompt = {
        "target_role": target_role,
        "metadata_contract": METADATA_CONTRACT,
        "instructions": [
            "metadata_contract.response_shape와 metadata_contract.categories에 정의된 category/field 이름만 사용해.",
            "CV 안의 정보를 metadata_contract.categories의 설명에 맞게 가능한 한 많이 채워.",
            "원문 문장을 그대로 raw_text에만 넣지 말고, 해당 문장 안의 학교/학위/전공/기간/기관/역할/성과/기술 등을 알맞은 field로 옮겨.",
            "raw_text는 근거 확인용이므로 각 item마다 짧게 유지하고, 실제 데이터는 나머지 field에 넣어.",
            "주관적 해석, 조언, 확인 필요, 보완 필요, URL 확인 필요 같은 문장은 어떤 field에도 쓰지 마.",
            "LinkedIn, GitHub, Portfolio는 정확한 URL 문자열이 PDF에 보이는 경우에만 other.content에 그대로 적어. 정확한 URL이 보이지 않으면 항목을 만들지 마.",
            "확정할 수 없는 값은 빈 문자열로 두고, 빈 항목은 만들지 마.",
        ],
    }
    body = json.dumps(
        {
            "model": OPENAI_MODEL,
            "input": [
                {"role": "system", "content": [{"type": "input_text", "text": system_prompt}]},
                {
                    "role": "user",
                    "content": [
                        {"type": "input_text", "text": json.dumps(user_prompt, ensure_ascii=False)},
                        {
                            "type": "input_file",
                            "filename": filename or "cv.pdf",
                            "file_data": f"data:application/pdf;base64,{encoded_pdf}",
                        },
                    ],
                },
            ],
            "max_output_tokens": 6000,
        },
        ensure_ascii=False,
    ).encode("utf-8")
    request = urllib.request.Request(
        OPENAI_ENDPOINT,
        data=body,
        method="POST",
        headers={
            "Authorization": f"Bearer {OPENAI_API_KEY}",
            "Content-Type": "application/json",
        },
    )
    with urllib.request.urlopen(request, timeout=60) as response:
        payload = json.loads(response.read().decode("utf-8"))
    fields = parse_json_object(response_output_text(payload))
    metadata_source = fields.get("metadata")
    if not metadata_source and any(category in fields for category in METADATA_SCHEMA):
        metadata_source = fields
    metadata = normalize_metadata(metadata_source or {})
    normalized_fields = {
        "targetRole": fields.get("targetRole") or target_role,
        "metadata": metadata,
        "education": ensure_bullet_text(fields.get("education", "")),
        "projects": ensure_bullet_text(fields.get("projects", "")),
        "work": ensure_bullet_text(fields.get("work", "")),
        "activity": ensure_bullet_text(fields.get("activity", "")),
        "strength": ensure_bullet_text(fields.get("strength", "")),
        "extra": ensure_bullet_text(fields.get("extra", "")),
        "rawSummary": clean_text(fields.get("rawSummary", "")),
    }
    combined_text = metadata_to_text(metadata) or "\n\n".join(str(value) for key, value in normalized_fields.items() if key != "metadata" and value)
    return combined_text, normalized_fields


def section_between(text_value, start_patterns, end_patterns):
    lowered = text_value.lower()
    starts = [lowered.find(pattern.lower()) for pattern in start_patterns]
    starts = [index for index in starts if index >= 0]
    if not starts:
        return ""
    start = min(starts)
    next_start = len(text_value)
    for pattern in end_patterns:
        index = lowered.find(pattern.lower(), start + 1)
        if index >= 0:
            next_start = min(next_start, index)
    return clean_text(text_value[start:next_start])[:1600]


def map_cv_text_to_fields(cv_text, target_role=""):
    education = section_between(
        cv_text,
        ["Education", "학력", "University", "B.S.", "Bachelor"],
        ["Research Experience", "Experience", "Publications", "Projects", "Honors", "Awards", "Activities"],
    )
    projects = "\n\n".join(
        item
        for item in [
            section_between(cv_text, ["Publications", "Publication"], ["Manuscripts", "Scholarships", "Honors", "Awards", "Leadership", "Activities"]),
            section_between(cv_text, ["Manuscripts", "Under Review"], ["Scholarships", "Honors", "Awards", "Leadership", "Activities"]),
            section_between(cv_text, ["Projects", "Project"], ["Experience", "Honors", "Awards", "Leadership", "Activities"]),
        ]
        if item
    )[:2400]
    work = section_between(
        cv_text,
        ["Research Experience", "Work Experience", "Experience", "Intern"],
        ["Publications", "Manuscripts", "Scholarships", "Honors", "Awards", "Leadership", "Activities"],
    )
    activity = "\n\n".join(
        item
        for item in [
            section_between(cv_text, ["Honors", "Awards", "Honors & Awards"], ["Leadership", "Service", "Activities", "Language"]),
            section_between(cv_text, ["Leadership", "Service"], ["Activities", "Language", "Skills"]),
            section_between(cv_text, ["Activities"], ["Language", "Skills"]),
        ]
        if item
    )[:2200]
    strengths = []
    signals = evidence_signals(cv_text)
    phrases = extract_keyphrases(cv_text, top_n=8)
    if phrases:
        strengths.append("핵심 표현: " + ", ".join(phrases[:6]))
    if signals:
        strengths.append("외부 증거: " + ", ".join(signals[:8]))

    mapped = {
        "targetRole": target_role,
        "education": education,
        "projects": projects,
        "work": work,
        "activity": activity,
        "strength": "\n".join(strengths),
        "extra": cv_text[:5000],
    }
    return mapped

def parse_analyze_request(headers, body):
    content_type = headers.get("Content-Type", "")
    if content_type.startswith("multipart/form-data"):
        fields, files = parse_multipart(body, content_type)
        target_role = fields.get("target_role", "")
        pdf_file = files.get("cv_file")
        cv_text = ""
        filename = ""
        pdf_meta = {"method": "manual", "pages": 0}
        mapped_fields = {}
        if pdf_file:
            filename = pdf_file["filename"]
            cv_text, mapped_fields = call_openai_pdf_field_mapping(
                pdf_file["content"],
                filename,
                target_role,
            )
            pdf_meta = {"method": "openai_input_file", "pages": None, "fields": mapped_fields}
        preferences = {"target_role": target_role, "preparation_period": "", "additional_user_input": ""}
        metadata = normalize_metadata(mapped_fields.get("metadata", {})) if pdf_file else {}
        return cv_text, target_role, filename, pdf_meta, metadata, preferences

    payload = json.loads(body.decode("utf-8") or "{}")
    preferences = payload.get("preferences") or {}
    target_role = payload.get("target_role") or preferences.get("target_role", "")
    cv_text = payload.get("cv_text", "")
    # Keep the structured user-confirmed metadata available to every downstream
    # agent, while retaining the existing text-based ranking pipeline.
    metadata = payload.get("metadata")
    metadata = normalize_metadata(metadata or {})
    if metadata:
        cv_text = f"{cv_text}\n\nConfirmed metadata:\n{json.dumps(metadata, ensure_ascii=False)}"
    if preferences:
        cv_text = f"{cv_text}\n\nUser preferences:\n{json.dumps(preferences, ensure_ascii=False)}"
    return cv_text, target_role, "", {"method": "manual", "pages": 0, "preferences": preferences}, metadata, preferences

class HICareerHandler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(ROOT), **kwargs)

    def do_GET(self):
        parsed_url = urllib.parse.urlparse(self.path)
        if parsed_url.path == "/api/jobs/popular":
            self.handle_popular_jobs(parsed_url)
            return
        super().do_GET()

    def do_POST(self):
        parsed_url = urllib.parse.urlparse(self.path)
        if parsed_url.path == "/api/analyze-cv-stream":
            self.handle_analyze_cv_stream()
            return
        if parsed_url.path == "/api/analyze-cv":
            self.handle_analyze_cv()
            return
        if parsed_url.path == "/api/extract-cv":
            self.handle_extract_cv()
            return
        self.send_error(404, "Not found")

    def handle_popular_jobs(self, parsed_url):
        query = urllib.parse.parse_qs(parsed_url.query)
        limit = int(query.get("limit", ["6"])[0])
        keyword = query.get("keyword", [DEFAULT_JOB_KEYWORD])[0]

        try:
            jobs = fetch_popular_jobs(limit, keyword)
            self.send_json(jobs)
        except (urllib.error.URLError, TimeoutError, ElementTree.ParseError, ValueError):
            self.send_json(FALLBACK_JOBS[:limit])

    def handle_extract_cv(self):
        content_length = int(self.headers.get("Content-Length", "0"))
        body = self.rfile.read(content_length)
        try:
            content_type = self.headers.get("Content-Type", "")
            fields, files = parse_multipart(body, content_type)
            target_role = fields.get("target_role", "")
            pdf_file = files.get("cv_file")
            if not pdf_file:
                self.send_json({"error": "PDF 파일이 필요합니다.", "text": "", "fields": {}}, status=400)
                return

            cv_text, mapped_fields = call_openai_pdf_field_mapping(
                pdf_file["content"],
                pdf_file["filename"],
                target_role,
            )
            self.send_json(
                {
                    "source": "openai_pdf",
                    "filename": pdf_file["filename"],
                    "pdf": {"method": "openai_input_file", "pages": None},
                    "text": cv_text,
                    "fields": mapped_fields,
                }
            )
        except ValueError as exc:
            self.send_json({"error": str(exc), "text": "", "fields": {}}, status=422)
        except (json.JSONDecodeError, urllib.error.URLError, TimeoutError) as exc:
            self.send_json({"error": "LLM PDF 정리에 실패했습니다. PDF 내용과 API 설정을 확인해주세요.", "text": "", "fields": {}}, status=502)

    def handle_analyze_cv(self):
        content_length = int(self.headers.get("Content-Length", "0"))
        body = self.rfile.read(content_length)
        cv_text = ""
        target_role = ""
        filename = ""
        pdf_meta = {"method": "unknown", "pages": 0}
        metadata = {}
        preferences = {}
        ranked_jobs = []

        try:
            cv_text, target_role, filename, pdf_meta, metadata, preferences = parse_analyze_request(self.headers, body)
            if not cv_text.strip():
                self.send_json(
                    {
                        "error": "CV 텍스트를 추출하지 못했습니다. 텍스트 기반 PDF를 업로드하거나 질문 입력을 사용해주세요.",
                        "rankedJobs": [],
                    },
                    status=422,
                )
                return

            keyword = target_role or " ".join(extract_profile_skills(cv_text)[:3]) or DEFAULT_JOB_KEYWORD
            jobs = fetch_popular_jobs(10, keyword)
            ranked_jobs = rank_jobs_for_cv(cv_text, jobs, target_role)
            agent = build_agent_result(cv_text, target_role, jobs, ranked_jobs)
            summary = build_cv_summary(cv_text, target_role) | {"pdf": pdf_meta}
            llm_report = safe_llm_report(cv_text, summary, ranked_jobs, agent)
            feedback_loop = safe_feedback_loop(cv_text, metadata, preferences, ranked_jobs)
            self.send_json(
                {
                    "source": "pdf" if filename else "manual",
                    "filename": filename,
                    "summary": summary,
                    "rankedJobs": ranked_jobs[:6],
                    "agent": agent,
                    "llmReport": llm_report,
                    "feedbackLoop": feedback_loop,
                }
            )
        except (json.JSONDecodeError, ValueError):
            self.send_json({"error": "요청 형식이 올바르지 않습니다.", "rankedJobs": []}, status=400)
        except (urllib.error.URLError, TimeoutError, ElementTree.ParseError):
            ranked_jobs = rank_jobs_for_cv(cv_text, FALLBACK_JOBS, target_role)
            agent = build_agent_result(cv_text, target_role, FALLBACK_JOBS, ranked_jobs)
            summary = build_cv_summary(cv_text, target_role) | {"pdf": pdf_meta}
            llm_report = safe_llm_report(cv_text, summary, ranked_jobs, agent)
            feedback_loop = safe_feedback_loop(cv_text, metadata, preferences, ranked_jobs)
            self.send_json(
                {
                    "source": "fallback",
                    "filename": filename,
                    "summary": summary,
                    "rankedJobs": ranked_jobs[:6],
                    "agent": agent,
                    "llmReport": llm_report,
                    "feedbackLoop": feedback_loop,
                }
            )

    def send_stream_headers(self):
        self.send_response(200)
        self.send_header("Content-Type", "application/x-ndjson; charset=utf-8")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("X-Accel-Buffering", "no")
        self.end_headers()

    def write_stream_event(self, event, payload):
        line = json.dumps({"event": event, "payload": payload}, ensure_ascii=False).encode("utf-8") + b"\n"
        self.wfile.write(line)
        self.wfile.flush()

    def handle_analyze_cv_stream(self):
        content_length = int(self.headers.get("Content-Length", "0"))
        body = self.rfile.read(content_length)
        cv_text = ""
        target_role = ""
        filename = ""
        pdf_meta = {"method": "unknown", "pages": 0}
        metadata = {}
        preferences = {}

        self.send_stream_headers()
        try:
            self.write_stream_event("status", {"message": "입력한 metadata와 preference를 읽고 있습니다."})
            cv_text, target_role, filename, pdf_meta, metadata, preferences = parse_analyze_request(self.headers, body)
            if not cv_text.strip():
                self.write_stream_event("error", {"message": "CV 텍스트를 추출하지 못했습니다. Metadata 항목을 하나 이상 입력해주세요."})
                return

            self.write_stream_event("status", {"message": "현재 공고 후보를 불러오고 CV와의 fit을 계산하고 있습니다."})
            keyword = target_role or " ".join(extract_profile_skills(cv_text)[:3]) or DEFAULT_JOB_KEYWORD
            jobs = fetch_popular_jobs(10, keyword)
            ranked_jobs = rank_jobs_for_cv(cv_text, jobs, target_role)
            agent = build_agent_result(cv_text, target_role, jobs, ranked_jobs)
            summary = build_cv_summary(cv_text, target_role) | {"pdf": pdf_meta}
            llm_report = safe_llm_report(cv_text, summary, ranked_jobs, agent)

            try:
                feedback_loop = build_feedback_loop(
                    cv_text,
                    metadata,
                    preferences,
                    ranked_jobs,
                    emit=self.write_stream_event,
                )
            except Exception:
                fallback_plan = fallback_consult_agent_plan(metadata, preferences, ranked_jobs, build_retrieval_context(ranked_jobs, target_role))
                fallback_consult = fallback_consult_agent_review(metadata, preferences, fallback_plan, {}, allow_revisions=False)
                feedback_loop = {
                    "mode": "fallback",
                    "retrievalPolicy": "consulting_source_registry_quality_gate",
                    "retrievedSources": fallback_plan.get("retrieved_sources", {}),
                    "supportingRetrievalResults": {},
                    "benchmark": fallback_plan.get("benchmark", {}),
                    "gapAnalysis": fallback_plan.get("gap_analysis", []),
                    "activatedAgents": fallback_plan.get("activated_agents", []),
                    "supportingReviews": {},
                    "consultResult": fallback_consult,
                    "leadingReport": fallback_leading_agent_final(preferences, fallback_consult).get("final_report", {}),
                    "conversationLog": fallback_plan.get("conversation_log", []) + fallback_consult.get("conversation_log", []),
                }
            self.write_stream_event(
                "final",
                {
                    "source": "pdf" if filename else "manual",
                    "filename": filename,
                    "summary": summary,
                    "rankedJobs": ranked_jobs[:6],
                    "agent": agent,
                    "llmReport": llm_report,
                    "feedbackLoop": feedback_loop,
                },
            )
        except (urllib.error.URLError, TimeoutError, ElementTree.ParseError):
            try:
                ranked_jobs = rank_jobs_for_cv(cv_text, FALLBACK_JOBS, target_role)
                agent = build_agent_result(cv_text, target_role, FALLBACK_JOBS, ranked_jobs)
                summary = build_cv_summary(cv_text, target_role) | {"pdf": pdf_meta}
                llm_report = safe_llm_report(cv_text, summary, ranked_jobs, agent)
                feedback_loop = safe_feedback_loop(cv_text, metadata, preferences, ranked_jobs)
                self.write_stream_event(
                    "final",
                    {
                        "source": "fallback",
                        "filename": filename,
                        "summary": summary,
                        "rankedJobs": ranked_jobs[:6],
                        "agent": agent,
                        "llmReport": llm_report,
                        "feedbackLoop": feedback_loop,
                    },
                )
            except Exception as exc:
                self.write_stream_event("final", {"source": "fallback", "filename": filename, "summary": build_cv_summary(cv_text, target_role) | {"pdf": pdf_meta}, "rankedJobs": ranked_jobs[:6], "agent": build_agent_result(cv_text, target_role, FALLBACK_JOBS, ranked_jobs), "llmReport": None, "feedbackLoop": safe_feedback_loop(cv_text, metadata, preferences, ranked_jobs)})
        except (json.JSONDecodeError, ValueError) as exc:
            self.write_stream_event("final", {"source": "manual", "filename": filename, "summary": build_cv_summary(cv_text, target_role) | {"pdf": pdf_meta}, "rankedJobs": [], "agent": build_agent_result(cv_text, target_role, [], []), "llmReport": None, "feedbackLoop": safe_feedback_loop(cv_text, metadata, preferences, [])})
        except Exception as exc:
            fallback_jobs = ranked_jobs or []
            self.write_stream_event(
                "final",
                {
                    "source": "fallback",
                    "filename": filename,
                    "summary": build_cv_summary(cv_text, target_role) | {"pdf": pdf_meta},
                    "rankedJobs": fallback_jobs[:6],
                    "agent": build_agent_result(cv_text, target_role, fallback_jobs, fallback_jobs),
                    "llmReport": None,
                    "feedbackLoop": safe_feedback_loop(cv_text, metadata, preferences, fallback_jobs),
                },
            )

    def send_json(self, payload, status=200):
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", f"public, max-age={CACHE_TTL_SECONDS}")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def end_headers(self):
        if urllib.parse.urlparse(self.path).path.endswith(".js"):
            self.send_header("Content-Type", mimetypes.types_map.get(".js", "application/javascript"))
        super().end_headers()


if __name__ == "__main__":
    server = ThreadingHTTPServer((HOST, PORT), HICareerHandler)
    print(f"HICAREER running at http://{HOST}:{PORT}")
    server.serve_forever()
